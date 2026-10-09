# -*- coding: utf-8 -*-
"""
Main entry point — starts all bots + Textual CLI dashboard.
Usage: python main.py [--debug] [--health-interval N]
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def parse_args():
    p = argparse.ArgumentParser(description="Multi-Site Bot System")
    p.add_argument("--debug", action="store_true", help="Enable debug-level console logging")
    p.add_argument("--health-interval", type=int, default=60,
                   help="Health check interval in seconds (default 60)")
    return p.parse_args()


ARGS = parse_args()

logging.basicConfig(
    level=logging.DEBUG if ARGS.debug else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def load_config():
    config_path = os.path.join(HERE, "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main():
    config = load_config()
    logger.info("Loading config...")

    # Apply debug level (--debug flag wins, else config debug_level,
    # else env BOT_DEBUG_LEVEL handled inside debug_utils, default INFO)
    level = "DEBUG" if ARGS.debug else config.get("debug_level", "INFO")
    try:
        from debug_utils import set_debug_level
        set_debug_level(level)
        logger.info(f"Debug level: {level}")
    except Exception as e:
        logger.warning(f"set_debug_level failed: {e}")

    # Init reply engine
    from reply_engine import ReplyEngine
    data_dir = config.get("data_dir", "")
    if data_dir and not os.path.isabs(data_dir):
        data_dir = os.path.join(HERE, data_dir)
    reply_engine = ReplyEngine(
        data_dir=data_dir,
        snap_username=config.get("snap_username", "username"),
        snap_after_n=config.get("snap_share_after_n_messages", 3),
    )
    logger.info(f"Reply engine: {reply_engine.template_count} templates, {reply_engine.category_count} categories")

    # Init proxy manager
    from proxy_manager import ProxyManager
    proxy_mgr = ProxyManager(config.get("proxy_file", "proxy.txt"))
    logger.info(f"Proxies: {proxy_mgr.total} loaded, {proxy_mgr.available_count} available")

    # Init database
    from db import Database
    db_path = config.get("db_path", "bot_data.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(ROOT, "data", db_path)
    db = Database(db_path)
    await db.init()

    # Init site settings in DB
    for site_name, site_cfg in config.get("sites", {}).items():
        await db.init_site_settings(site_name, {
            "max_sessions": site_cfg.get("max_sessions", 5),
            "reply_delay_min": config.get("reply_delay_min_sec", 2),
            "reply_delay_max": config.get("reply_delay_max_sec", 6),
            "snap_after_n": config.get("snap_share_after_n_messages", 3),
            "headless": 1 if site_cfg.get("headless", True) else 0,
            "enabled": 1 if site_cfg.get("enabled", False) else 0,
        })

    # Init Fixed SMS Engine
    from fixed_sms_engine import FixedSmsEngine
    fixed_engine = FixedSmsEngine(db, config)
    fsm_cfg = config.get("fixed_sms", {})
    if fsm_cfg.get("folder"):
        result = await fixed_engine.set_folder(fsm_cfg["folder"])
        if result.get("ok"):
            logger.info(f"FixedSms folder loaded: {result['files'].__len__()} files")
        else:
            logger.warning(f"FixedSms folder load failed: {result.get('error')}")
    snap = await fixed_engine.load_snap_username()
    logger.info(f"FixedSms: enabled={fixed_engine.is_enabled()}, snap={snap}")

    # Init DB Reply Engine
    db_reply_engine = None
    try:
        from db_reply_engine import DbReplyEngine
        db_reply_engine = DbReplyEngine(db, reply_engine)
        await db_reply_engine.init()
        logger.info("DB Reply Engine initialized")
    except Exception as e:
        logger.warning(f"DB Reply Engine init failed: {e}")

    # Init Mood Manager
    mood_manager = None
    try:
        from mood_manager import MoodManager
        mood_manager = MoodManager(db)
        await mood_manager.init()
        logger.info("Mood Manager initialized")
    except Exception as e:
        logger.warning(f"Mood Manager init failed: {e}")

    # Init Thread Manager
    thread_manager = None
    try:
        from thread_manager import ThreadManager
        thread_manager = ThreadManager(db)
        await thread_manager.init()
        logger.info("Thread Manager initialized")
    except Exception as e:
        logger.warning(f"Thread Manager init failed: {e}")

    # Init bots
    bots = {}
    sites_config = config.get("sites", {})

    # Pass shared config to each bot
    shared = {
        "snap_username": config.get("snap_username", "username"),
        "snap_share_after_n_messages": config.get("snap_share_after_n_messages", 3),
        "reply_delay_min_sec": config.get("reply_delay_min_sec", 2),
        "reply_delay_max_sec": config.get("reply_delay_max_sec", 6),
        "use_proxy": config.get("use_proxy", True),
    }

    for site_name, site_cfg in sites_config.items():
        if not site_cfg.get("enabled", False):
            logger.info(f"Site {site_name}: disabled, skipping")
            continue

        site_cfg = {**site_cfg, **shared}
        method = site_cfg.get("method", "")

        if method == "http_api" and site_name == "joingy":
            from sites.joingy import JoingyBot
            bots[site_name] = JoingyBot(site_cfg, reply_engine, db, proxy_mgr, fixed_engine=fixed_engine)
            logger.info(f"Loaded JoingyBot (HTTP API, max_sessions={site_cfg.get('max_sessions', 20)})")

        elif method == "playwright" and site_name == "isexychat":
            from sites.isexychat import IsexychatBot
            bots[site_name] = IsexychatBot(site_cfg, reply_engine, db, proxy_mgr, fixed_engine=fixed_engine)
            logger.info(f"Loaded IsexychatBot (Playwright, max_sessions={site_cfg.get('max_sessions', 5)})")

        else:
            logger.warning(f"Site {site_name}: method={method} not implemented yet")

    # Init dashboard
    from dashboard.cli import BotDashboard
    config_path = os.path.join(HERE, "config.json")
    app = BotDashboard(bots, db, proxy_mgr, reply_engine, config, config_path=config_path, fixed_engine=fixed_engine,
                       db_reply_engine=db_reply_engine, mood_manager=mood_manager, thread_manager=thread_manager)

    logger.info("Starting CLI dashboard...")

    # Background health check loop
    async def health_loop():
        while True:
            await asyncio.sleep(ARGS.health_interval)
            for name, bot in bots.items():
                if hasattr(bot, 'health_check'):
                    try:
                        result = await bot.health_check()
                        dead = result.get("dead", 0)
                        if dead > 0:
                            logger.warning(f"Health: {name} cleaned {dead} dead sessions")
                    except Exception as e:
                        logger.debug(f"Health check {name} error: {e}")

    health_task = asyncio.create_task(health_loop())

    # Autostart bots if configured
    if config.get("autostart", False):
        logger.info("Autostarting bots...")
        for name, bot in bots.items():
            if not bot.running:
                asyncio.create_task(bot.start())

    try:
        await app.run_async()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        health_task.cancel()
        for name, bot in bots.items():
            await bot.stop()
        await db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("  Multi-Site Bot System — CLI Dashboard")
    if ARGS.debug:
        print("  [DEBUG MODE] verbose console logging enabled")
    print("=" * 60)
    asyncio.run(main())