#!/usr/bin/env python3
# skills/research/argus/cli/daily_processor.py
"""Daily Argus end-to-end processing CLI.

Usage:
    python -m skills.research.argus.cli.daily_processor 2026-03-11
    python -m skills.research.argus.cli.daily_processor
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add workspace to path for direct script execution.
sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from skills.data.data_interface import MongoReader, MongoWriter
from skills.data.portfolio import PortfolioTransformer
from skills.infra import format_date, get_latest_trading_day, get_logger, parse_date
from skills.research.argus.config import ARGUS_CONFIG
from skills.research.argus.core import (
    ConsensusEngine,
    BayesianScorer,
    CredibilityScorer,
    CrowdingAnalyzer,
    DarwinDetector,
    IndustryWeightCalculator,
    PoolManager,
    RebalancingDetector,
    SignalGenerator,
    ConsensusDirectionEngine,
)

logger = get_logger('argus', 'research/argus')


def process_date(
    target_date: str,
    reader: Optional[MongoReader] = None,
    writer: Optional[MongoWriter] = None,
    output_dir: Optional[Path] = None,
    write_mongo: bool = True,
    stock_pool_ingestion: Optional[Any] = None,
) -> dict:
    """Process Argus for a single date from Mongo input to Mongo/JSON output."""
    logger.info("[Argus] Starting daily processing for %s", target_date)

    date_to_process = get_latest_trading_day(target_date)
    previous_date = _previous_trading_day(date_to_process)
    writer_injected = writer is not None
    reader = reader or MongoReader(database=ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents'))

    transformer = PortfolioTransformer()
    credibility_scorer = CredibilityScorer()
    signal_generator = SignalGenerator(credibility_scorer)
    pool_manager = PoolManager()
    rebalancing_detector = RebalancingDetector()
    darwin_detector = DarwinDetector()
    consensus_engine = ConsensusEngine(pool_manager)
    crowding_analyzer = CrowdingAnalyzer()
    consensus_direction_engine = ConsensusDirectionEngine()

    results = {
        'date': date_to_process,
        'previous_date': previous_date,
        'baseline_30d_date': None,
        'products_processed': 0,
        'signals_generated': 0,
        'industry_weights_written': 0,
        'industry_weights_generated': 0,
        'credential_scores_written': 0,
        'signals_written': 0,
        'signal_pool_written': 0,
        'stock_pool_written': 0,
        'portfolio_stock_pool_sync': None,
        'pool_summary': {},
        'output_file': None,
    }

    positions = reader.read(date_to_process, collection_name='portfolio_position')
    if not positions:
        logger.warning("[Argus] No position data for %s", date_to_process)
        return results

    trades = reader.read(date_to_process, collection_name='portfolio_trade')
    product_profiles = _read_product_profiles(reader, date_to_process)
    previous_positions = reader.read(previous_date, collection_name='portfolio_position')
    baseline_30d_date = _get_baseline_date(date_to_process, 30)
    results['baseline_30d_date'] = baseline_30d_date
    baseline_30d_weights = _read_industry_weights(reader, baseline_30d_date)
    baseline_60d_date = _get_baseline_date(date_to_process, 60)
    results['baseline_60d_date'] = baseline_60d_date
    baseline_60d_weights = _read_industry_weights(reader, baseline_60d_date)
    previous_weights = _read_industry_weights(reader, previous_date)

    product_name_lookup = _build_product_name_lookup(reader)
    _attach_product_names(positions, product_name_lookup)
    sector_info = _read_sector_info(reader)
    industry_weight_records = IndustryWeightCalculator.calculate(
        date_to_process,
        positions,
        sector_info,
        previous_weights=previous_weights,
        lookback_30d_weights=baseline_30d_weights,
        lookback_60d_weights=baseline_60d_weights,
        previous_positions=previous_positions,
    )
    results['industry_weights_generated'] = len(industry_weight_records)

    if write_mongo:
        writer = writer or MongoWriter(database=ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents'))
        writer.ensure_argus_indexes()
        results['industry_weights_written'] = writer.write_argus_industry_weights(industry_weight_records)

    product_codes = sorted({p['product_code'] for p in positions if p.get('product_code')})
    positions_by_product = _group_by_product(positions)
    previous_by_product = _group_by_product(previous_positions)
    trades_by_product_stock = _build_trade_lookup(trades)
    all_product_positions = [positions_by_product[code] for code in product_codes]

    all_signals: List[Dict] = []
    credential_records: List[Dict] = []

    for product_code in product_codes:
        current_pos = positions_by_product[product_code]
        previous_pos = previous_by_product.get(product_code, [])
        product_name = product_name_lookup.get(product_code, transformer.get_product_alias(product_code))
        position_changes = transformer.calculate_holding_ratio_change(current_pos, previous_pos)
        _attach_trade_directions(position_changes, trades_by_product_stock)
        rebalancing_events = rebalancing_detector.detect_rebalancing(position_changes, previous_pos)
        darwin_moment = darwin_detector.detect_darwin_moment(position_changes, all_product_positions)
        credibility_score = credibility_scorer.calculate_score(product_code, position_changes)

        credential_records.append(_credential_record(date_to_process, product_code, product_name, credibility_score, position_changes, credibility_scorer))

        signals = signal_generator.generate_signals(
            product_code=product_code,
            product_name=product_name,
            position_changes=position_changes,
            trade_date=date_to_process,
            pool_zone='SCAN',
            darwin_moment=darwin_moment,
            consensus_direction='NEUTRAL',
        )
        for signal in signals:
            signal['date'] = date_to_process
            signal['metadata']['rebalancing_events_count'] = len(rebalancing_events)
        all_signals.extend(signals)

    consensus = consensus_engine.calculate_consensus(all_signals)
    crowding = crowding_analyzer.analyze(positions, trades, all_signals)
    stock_pool_records = _build_stock_pool_records(
        date_to_process,
        all_signals,
        consensus,
        crowding,
        pool_manager,
    )
    stock_pool_records = BayesianScorer(product_profiles=product_profiles).score_signal_pool_records(
        stock_pool_records,
        all_signals,
    )
    _annotate_signals(all_signals, stock_pool_records, consensus, crowding)

    current_pool = {zone: set() for zone in PoolManager.ZONES}
    for record in stock_pool_records:
        current_pool[record['pool_zone']].add(record['wind_code'])

    results.update({
        'products_processed': len(product_codes),
        'signals_generated': len(all_signals),
        'pool_summary': pool_manager.get_pool_summary(current_pool),
    })

    if write_mongo:
        writer = writer or MongoWriter(database=ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents'))
        writer.ensure_argus_indexes()
        results['credential_scores_written'] = writer.write_argus_credential_scores(credential_records)
        results['signals_written'] = writer.write_argus_signals(all_signals)


        # Phase 4B: Darwin Moment Detection
        index_quotes = _read_index_quotes(reader, date_to_process)
        darwin_events = darwin_detector.detect_for_date(
            date_to_process,
            index_quotes=index_quotes,
            credential_scores=credential_records,
            industry_weights=industry_weight_records,
        )
        results['darwin_events_written'] = writer.write_argus_darwin_events(darwin_events) if darwin_events else 0

        # Phase 4C: Consensus Direction Engine
        consensus_direction = consensus_direction_engine.calculate_for_date(
            date_to_process,
            industry_weight_records,
        )
        results['consensus_direction_written'] = writer.write_argus_consensus_direction([consensus_direction])
        results['consensus_direction_signal'] = consensus_direction.get('prosperity_signal', 'NEUTRAL')


        # Build wind_code -> sw1_code mapping for Darwin event matching
        wind_to_sw1 = _build_windcode_to_sw1_lookup(sector_info)


        # Enrich stock pool with Darwin/prosperity info before writing
        _enrich_stock_pool_with_darwin_prosperity(
            stock_pool_records, darwin_events, consensus_direction, wind_to_sw1
        )
        previous_signal_pool = reader.read(previous_date, collection_name='08_research_argus_signal_pool')
        results['signal_pool_written'] = _write_argus_signal_pool(writer, stock_pool_records)
        results['stock_pool_written'] = results['signal_pool_written']

        # Phase 5: Portfolio stock-pool incremental sync and audit.
        ingestion = stock_pool_ingestion
        if ingestion is None and not writer_injected:
            ingestion = _default_stock_pool_ingestion()
        if ingestion is not None:
            results['portfolio_stock_pool_sync'] = ingestion.ingest_signals_incremental(
                current_signals=stock_pool_records,
                previous_signals=previous_signal_pool,
                actor='system:argus',
            )

        logger.info(
            '[Argus] Phase 4B: %d Darwin events, Phase 4C: prosperity=%s, Phase 5 sync=%s',
            len(darwin_events),
            consensus_direction.get('prosperity_signal', 'NEUTRAL'),
            results['portfolio_stock_pool_sync'],
        )

    output_file = _write_json_output(
        date_to_process,
        all_signals,
        consensus,
        crowding,
        stock_pool_records,
        results,
        output_dir,
        consensus_direction=None,
    )
    results['output_file'] = str(output_file)

    logger.info("[Argus] Processing complete: %s signals generated", len(all_signals))
    return results


def _previous_trading_day(date_to_process: str) -> str:
    previous_calendar_day = parse_date(date_to_process) - timedelta(days=1)
    return get_latest_trading_day(format_date(previous_calendar_day))


def _next_trading_day(date_to_process: str) -> str:
    """Return the next trading day after the given date."""
    next_calendar_day = parse_date(date_to_process) + timedelta(days=1)
    return get_latest_trading_day(format_date(next_calendar_day))


def _get_latest_argus_signal_pool_date(reader: MongoReader) -> Optional[str]:
    """Get the latest date in argus_signal_pool collection."""
    collection_name = ARGUS_CONFIG.get('mongo', {}).get('collections', {}).get('signal_pool', '08_research_argus_signal_pool')
    try:
        dates = reader.db[collection_name].distinct('date')
        if dates:
            return max(str(d) for d in dates)
    except Exception as e:
        logger.warning("[Argus CLI] Failed to get latest argus_signal_pool date: %s", e)
    return None


def _credential_record(
    date_to_process: str,
    product_code: str,
    product_name: str,
    credibility_score: float,
    position_changes: List[Dict],
    credibility_scorer: Optional[CredibilityScorer] = None,
) -> Dict:
    if credibility_scorer is None:
        credibility_scorer = CredibilityScorer()
    return {
        'date': date_to_process,
        'product_code': product_code,
        'product_name': product_name,
        'credibility_score': round(credibility_score, 4),
        'confidence_level': credibility_scorer.get_confidence_level(credibility_score),
        'positions_count': len(position_changes),
        'avg_abs_holding_ratio_change': round(
            sum(abs(p.get('holding_ratio_change', 0) or 0) for p in position_changes) / len(position_changes),
            6,
        ) if position_changes else 0.0,
    }



def _group_by_product(records: List[Dict]) -> Dict[str, List[Dict]]:
    grouped = defaultdict(list)
    for record in records:
        product_code = record.get('product_code')
        if product_code:
            grouped[product_code].append(record)
    return grouped


def _build_trade_lookup(trades: List[Dict]) -> Dict[tuple, str]:
    lookup = {}
    for trade in trades:
        product_code = trade.get('product_code')
        wind_code = trade.get('asset_wind_code') or trade.get('wind_code')
        if not product_code or not wind_code:
            continue
        direction = _normalize_trade_direction(trade.get('trade_direction') or trade.get('direction'))
        lookup[(product_code, wind_code)] = direction
    return lookup


def _attach_trade_directions(position_changes: List[Dict], trades_by_product_stock: Dict[tuple, str]) -> None:
    for position_change in position_changes:
        key = (
            position_change.get('product_code'),
            position_change.get('asset_wind_code') or position_change.get('wind_code'),
        )
        trade_direction = trades_by_product_stock.get(key)
        if trade_direction:
            position_change['trade_direction'] = trade_direction


def _normalize_trade_direction(direction: Any) -> str:
    direction_text = str(direction or '').upper()
    if 'BUY' in direction_text or '买' in direction_text:
        return 'BUY'
    if 'SELL' in direction_text or '卖' in direction_text:
        return 'SELL'
    return 'HOLD'


def _read_product_profiles(reader: MongoReader, date_to_process: str) -> List[Dict]:
    collection_name = '08_research_argus_product_profile'
    if hasattr(reader, 'read'):
        profiles = reader.read(date_to_process, collection_name=collection_name)
        if profiles:
            return profiles
    db = getattr(reader, 'db', None)
    if db is None:
        return []
    collection = db[collection_name]
    query = {'date': {'$lte': date_to_process}}
    profiles = list(collection.find(query, {'_id': 0}).sort('date', -1))
    return profiles or list(collection.find({}, {'_id': 0}))


def _get_baseline_date(date_to_process: str, days: int) -> str:
    target = parse_date(date_to_process) - timedelta(days=days + 5)
    return get_latest_trading_day(format_date(target))



def _read_sector_info(reader: MongoReader) -> List[Dict]:
    industry_config = ARGUS_CONFIG.get('industry_weight', {})
    classify_system = industry_config.get('classify_system', 'SW')
    collection_name = industry_config.get('sector_info_collection', 'stock_sector_info')
    if hasattr(reader, 'read_sector_info'):
        return reader.read_sector_info(classify_system=classify_system, collection_name=collection_name)
    logger.warning("[Argus] Reader does not support sector info; unmapped stocks will use UNKNOWN")
    return []



def _read_industry_weights(reader: MongoReader, date_to_read: Optional[str]) -> List[Dict]:
    if not date_to_read:
        return []
    if hasattr(reader, 'read_industry_weights'):
        return reader.read_industry_weights(date_to_read)
    logger.warning("[Argus] Reader does not support industry weights; baseline %s unavailable", date_to_read)
    return []


def _write_argus_signal_pool(writer: MongoWriter, stock_pool_records: List[Dict]) -> int:
    if hasattr(writer, 'write_argus_signal_pool'):
        return writer.write_argus_signal_pool(stock_pool_records)
    return writer.write_argus_stock_pool(stock_pool_records)


def _default_stock_pool_ingestion() -> Any:
    from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
    from skills.portfolio.stock_pool.repository import StockPoolRepository
    from skills.portfolio.stock_pool.service import StockPoolService

    database = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
    return StockPoolIngestionService(StockPoolService(StockPoolRepository(database=database)))



def _read_index_quotes(reader: MongoReader, date_to_read: str) -> List[Dict]:
    # Read CSI300 + all SW Level1 codes for 20d lookback window
    end_dt = parse_date(date_to_read)
    start_dt = end_dt - timedelta(days=25)
    start_date = format_date(start_dt)
    end_date = date_to_read
    
    codes_to_read = ['000300.SH'] + [
        '801010.SI', '801030.SI', '801040.SI', '801050.SI', '801080.SI',
        '801110.SI', '801120.SI', '801130.SI', '801140.SI', '801150.SI',
        '801160.SI', '801170.SI', '801180.SI', '801200.SI', '801210.SI',
        '801230.SI', '801710.SI', '801720.SI', '801730.SI', '801740.SI',
        '801750.SI', '801760.SI', '801770.SI', '801780.SI', '801790.SI',
        '801880.SI', '801890.SI', '801950.SI', '801960.SI', '801970.SI',
        '801980.SI',
    ]
    all_quotes = []
    for code in codes_to_read:
        if hasattr(reader, 'read_index_quotes'):
            quotes = reader.read_index_quotes(code, start_date, end_date)
            all_quotes.extend(quotes)
    if not all_quotes:
        logger.warning("[Argus] No index quotes loaded; Darwin detection may not work")
    return all_quotes



def _build_product_name_lookup(reader: MongoReader) -> Dict[str, str]:
    """Build product_code -> product_name lookup from portfolio_basic_info.

    1. Read product_name from portfolio_basic_info (e.g., "JS-001")
    2. Extract prefix (JS) and map to full name via PRODUCT_ALIAS (景顺)
    3. Reconstruct: 景顺-001
    """
    from skills.research.argus.config import PRODUCT_ALIAS

    db = getattr(reader, 'db', None)
    if db is not None:
        col = db['portfolio_basic_info']
        docs = list(col.find({}, {'product_code': 1, 'product_name': 1, '_id': 0}))
        lookup = {}
        for doc in docs:
            code = doc.get('product_code')
            raw_name = doc.get('product_name') or doc.get('name') or ''
            if not code or not raw_name:
                continue

            # Extract prefix (JS from "JS-001", SM from "SM001")
            if '-' in raw_name:
                prefix = raw_name.split('-')[0]
            elif raw_name.startswith('SM'):
                prefix = raw_name[:2]
            else:
                prefix = raw_name

            # Map prefix to full name
            full_prefix = PRODUCT_ALIAS.get(prefix, prefix)

            # Reconstruct: 景顺-001
            if '-' in raw_name:
                suffix = raw_name.split('-', 1)[1]
                lookup[code] = f"{full_prefix}-{suffix}"
            else:
                lookup[code] = full_prefix

        logger.info(f"[product_name] Loaded {len(lookup)} products from portfolio_basic_info")
        for code, name in lookup.items():
            logger.info(f"[product_name]   {code} -> {name}")
    else:
        lookup = {}

    return lookup


def _attach_product_names(positions: List[Dict], product_name_lookup: Dict[str, str]) -> None:
    for position in positions:
        product_code = position.get('product_code')
        if product_code and not position.get('product_name'):
            position['product_name'] = product_name_lookup.get(product_code, product_code)


def _build_windcode_to_sw1_lookup(sector_info: List[Dict]) -> Dict[str, str]:
    from skills.research.argus.core.industry_weight_calculator import IndustryWeightCalculator
    lookup = {}
    for item in sector_info:
        sw1_code = IndustryWeightCalculator._normalize_sw1_code(
            item.get('sw1_code') or item.get('l1_code') or item.get('sector_code')
        )
        if not sw1_code:
            continue
        for key in (
            item.get('full_symbol'),
            item.get('asset_wind_code'),
            item.get('wind_code'),
            item.get('symbol'),
            item.get('code'),
        ):
            if key:
                lookup[str(key)] = sw1_code
    return lookup


def _enrich_stock_pool_with_darwin_prosperity(
    stock_pool_records: List[Dict],
    darwin_events: List[Dict],
    consensus_direction: Dict,
    wind_to_sw1: Optional[Dict[str, str]] = None,
) -> None:
    darwin_by_sector: Dict[str, Dict] = {e.get('sw1_code'): e for e in darwin_events}
    prosperity_signal = consensus_direction.get('prosperity_signal', 'NEUTRAL')

    for record in stock_pool_records:
        record['prosperity_signal'] = prosperity_signal

        wind_code = record.get('wind_code')
        if wind_to_sw1 and wind_code:
            sw1_code = wind_to_sw1.get(wind_code)
            if sw1_code and sw1_code in darwin_by_sector:
                event = darwin_by_sector[sw1_code]
                record['darwin_moment'] = True
                record['darwin_confidence'] = event.get('confidence')
                record['darwin_event_id'] = f"{event.get('date')}_{event.get('sw1_code')}"
            else:
                record['darwin_moment'] = False
                record['darwin_confidence'] = None
                record['darwin_event_id'] = None
        else:
            record['darwin_moment'] = False
            record['darwin_confidence'] = None
            record['darwin_event_id'] = None


def _build_stock_pool_records(
    date_to_process: str,
    signals: List[Dict],
    consensus: Dict[str, Dict],
    crowding: Dict[str, Dict],
    pool_manager: PoolManager,
) -> List[Dict]:
    stock_signals = defaultdict(list)
    stock_names = {}
    for signal in signals:
        for target in signal.get('target_stocks', []):
            wind_code = target.get('wind_code')
            if not wind_code:
                continue
            stock_signals[wind_code].append(signal)
            stock_names[wind_code] = target.get('stock_name') or stock_names.get(wind_code, '')

    records = []
    for wind_code, related_signals in stock_signals.items():
        products = sorted({signal.get('product_code') for signal in related_signals if signal.get('product_code')})
        confidence = max(signal.get('confidence', 0) for signal in related_signals)
        darwin_moment = any(signal.get('metadata', {}).get('darwin_moment') for signal in related_signals)
        pool_zone = pool_manager.classify_stock(
            wind_code,
            stock_names.get(wind_code, ''),
            confidence,
            products,
            darwin_moment,
        )
        crowding_data = crowding.get(wind_code, {})
        consensus_data = consensus.get(wind_code, {})
        records.append({
            'date': date_to_process,
            'wind_code': wind_code,
            'stock_name': stock_names.get(wind_code, ''),
            'pool_zone': pool_zone,
            'confidence': round(confidence, 4),
            'contributing_products': products,
            'contributing_products_count': len(products),
            'consensus_direction': consensus_data.get('direction', 'NEUTRAL'),
            'consensus_confidence': round(consensus_data.get('confidence', 0), 4),
            'crowding_score': crowding_data.get('crowding_score', 0),
            'crowding_level': crowding_data.get('crowding_level', 'LOW'),
            'crowding_layers': crowding_data.get('layer_scores', {}),
            'darwin_moment': darwin_moment,
        })
    return records


def _annotate_signals(
    signals: List[Dict],
    stock_pool_records: List[Dict],
    consensus: Dict[str, Dict],
    crowding: Dict[str, Dict],
) -> None:
    pool_by_stock = {record['wind_code']: record for record in stock_pool_records}
    for signal in signals:
        target = (signal.get('target_stocks') or [{}])[0]
        wind_code = target.get('wind_code')
        if not wind_code:
            continue
        pool_record = pool_by_stock.get(wind_code, {})
        crowding_data = crowding.get(wind_code, {})
        signal['metadata'].update({
            'crowding_level': crowding_data.get('crowding_level', 'LOW'),
            'crowding_score': crowding_data.get('crowding_score', 0),
            'crowding_layers': crowding_data.get('layer_scores', {}),
            'pool_zone': pool_record.get('pool_zone', signal['metadata'].get('pool_zone', 'SCAN')),
            'contributing_products_count': pool_record.get('contributing_products_count', 1),
            'consensus_direction': _signal_consensus_label(consensus.get(wind_code, {}).get('direction', 'NEUTRAL')),
        })


def _signal_consensus_label(direction: str) -> str:
    return {'BUY': 'BULLISH', 'SELL': 'BEARISH', 'HOLD': 'NEUTRAL'}.get(direction, direction)


def _write_json_output(
    date_to_process: str,
    signals: List[Dict],
    consensus: Dict[str, Dict],
    crowding: Dict[str, Dict],
    stock_pool_records: List[Dict],
    results: Dict,
    output_dir: Optional[Path],
    consensus_direction: Optional[Dict] = None,
) -> Path:
    output_dir = output_dir or Path('/home/pascal/.openclaw/workspace-yquant/logs/research/argus')
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f'argus_signal_{date_to_process.replace("-", "")}.json'
    output_data = {
        'generated_at': datetime.now().isoformat(),
        'date': date_to_process,
        'signals': signals,
        'consensus': consensus,
        'crowding': crowding,
        'stock_pool': stock_pool_records,
        'pool_summary': results.get('pool_summary', {}),
    }
    if consensus_direction:
        output_data['consensus_direction'] = consensus_direction
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    return output_file


def main():
    """CLI entry point.
    
    Usage:
        python -m skills.research.argus.cli.daily_processor          # auto: 从 argus_signal_pool 最新日期跑到现在
        python -m skills.research.argus.cli.daily_processor 2026-05-25  # 指定日期
    """
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    
    if target_date is None:
        # 自动模式：从 argus_signal_pool 最新日期开始，跑到今天或遇到无数据日
        logger.info("[Argus CLI] Auto mode: 从 argus_signal_pool 最新日期开始增量跑")
        
        database = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
        reader = MongoReader(database=database)
        
        # 获取 argus_signal_pool 最新日期
        latest_processed = _get_latest_argus_signal_pool_date(reader)
        if latest_processed is None:
            latest_processed = ARGUS_CONFIG.get('signal_pool', {}).get('bootstrap_date', '2025-12-31')
            logger.info("[Argus CLI] No existing argus_signal_pool found, using bootstrap: %s", latest_processed)
        
        start_date = _next_trading_day(latest_processed)
        end_date = format_date(datetime.now().date())
        
        logger.info("[Argus CLI] 开始增量处理: %s ~ %s", start_date, end_date)
        
        trading_days = get_trading_dates(start_date, end_date)
        processed = 0
        
        for trade_date in trading_days:
            positions = reader.read(trade_date, collection_name='portfolio_position')
            if not positions:
                logger.info("[Argus CLI] %s 无持仓数据，跳过", trade_date)
                continue
            
            try:
                results = process_date(trade_date, write_mongo=True)
                processed += 1
                logger.info("[Argus CLI] %s 完成: %d products, %d signals", 
                           trade_date, results['products_processed'], results['signals_generated'])
            except Exception as e:
                logger.error("[Argus CLI] %s 处理失败: %s", trade_date, e)
                break
        
        print(f"\n=== Argus 增量处理完成 ===")
        print(f"处理日期范围: {start_date} ~ {end_date}")
        print(f"处理天数: {processed}")
        print(f"跳过天数: {len(trading_days) - processed}")
        print(f"到达今天: {end_date}")
        
    else:
        # 指定日期模式
        logger.info("[Argus CLI] 指定日期模式: %s", target_date)
        try:
            results = process_date(target_date, write_mongo=True)
            print("\n=== Argus Processing Results ===")
            print(f"Date: {results['date']}")
            print(f"Products: {results['products_processed']}")
            print(f"Signals: {results['signals_generated']}")
            print(f"Credential Scores Written: {results['credential_scores_written']}")
            print(f"Signals Written: {results['signals_written']}")
            print(f"Signal Pool Written: {results['signal_pool_written']}")
            print(f"Consensus Direction: {results.get('consensus_direction_signal', 'N/A')}")
            print(f"Pool: {results['pool_summary']}")
            print(f"Output: {results['output_file']}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
