import asyncio
import logging
import os
import threading
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token: str, chat_id: str, engine=None):
        self.token = token
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.engine = engine
        self._app: Optional[Application] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self.startup_text: str = ""
        self._ready = False
        self._send_queue: list = []

    def _build_keyboard(self):
        return ReplyKeyboardMarkup(
            [
                ["📊 Status", "⏸ Pause", "▶ Resume"],
                ["🛑 Stop", "📋 Positions", "📋 Logs"],
            ],
            resize_keyboard=True,
            is_persistent=True,
        )

    def start(self):
        if not self.token or not self.chat_id:
            logger.info("Telegram bot not configured — skipping")
            return
        self._thread = threading.Thread(target=self._run_polling, daemon=True)
        self._thread.start()
        logger.info("Telegram bot thread started")

    def stop(self):
        if self._app:
            self._app.stop()

    def send(self, text: str):
        if not self._app or not self._loop:
            self._send_queue.append(text)
            logger.debug("Telegram not ready — queued message")
            return
        if not self._ready:
            self._send_queue.append(text)
            logger.debug("Telegram not ready — queued message")
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send(text), self._loop)
        except RuntimeError:
            logger.debug("Telegram send skipped — interpreter shutting down")

    async def _send(self, text: str):
        try:
            await self._app.bot.send_message(
                chat_id=self.chat_id, text=text,
                reply_markup=self._build_keyboard(),
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def _flush_queue(self):
        for text in self._send_queue:
            try:
                await self._app.bot.send_message(
                    chat_id=self.chat_id, text=text,
                    reply_markup=self._build_keyboard(),
                )
            except Exception as e:
                logger.warning(f"Telegram flush failed for queued message: {e}")
        self._send_queue.clear()

    async def _reply(self, update: Update, text: str):
        try:
            await update.message.reply_text(text, reply_markup=self._build_keyboard())
        except Exception as e:
            logger.error(f"Telegram reply error: {e}")

    def _run_polling(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._app = ApplicationBuilder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("pause", self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("logs", self._cmd_logs))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_button))
        logger.info("Telegram bot polling...")
        try:
            self._loop.run_until_complete(self._manual_poll())
        except Exception as e:
            logger.error(f"Telegram polling error: {e}")

    async def _manual_poll(self):
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        self._ready = True
        if self.startup_text:
            try:
                await self._app.bot.send_message(
                    chat_id=self.chat_id, text=self.startup_text,
                    reply_markup=self._build_keyboard(),
                )
                logger.info("Startup notification sent via Telegram")
            except Exception as e:
                logger.warning(f"Startup notification failed: {e}")
        await self._flush_queue()
        await asyncio.Event().wait()

    # ── Command handlers ──

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        msg = (
            "🤖 *Bot Active*\n\n"
            "I'll send you notifications when trades are entered or closed.\n"
            "Use the buttons below to control the bot."
        )
        await self._reply(update, msg)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        if not self.engine:
            await self._reply(update, "Engine not available")
            return
        mode = self.engine.config.get("mode", "?").upper()
        open_count = sum(1 for p in self.engine.positions.values() if p is not None)
        status_parts = []
        if self.engine._stopped:
            status_parts.append("STOPPED")
        elif self.engine._paused:
            status_parts.append("PAUSED")
        else:
            status_parts.append("RUNNING")
        status_tag = " | ".join(status_parts) if status_parts else "RUNNING"
        msg = (
            f"🤖 Bot Status [{status_tag}]\n"
            f"Mode: {mode}\n"
            f"Symbols: {len(self.engine.symbols)}\n"
            f"Open: {open_count}\n"
            f"Equity: ${self.engine.executor.equity:.2f}"
        )
        await self._reply(update, msg)

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        if self.engine:
            self.engine._paused = True
        await self._reply(update, "⏸ Bot paused — no new entries. Existing trades still managed.")

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        if self.engine:
            self.engine._paused = False
            self.engine._stopped = False
        await self._reply(update, "▶ Bot resumed — new entries enabled.")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        if self.engine:
            self.engine._stopped = True
        await self._reply(update, "🛑 Bot will stop after current tick. Existing trades continue until SL/TP.")

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        if not self.engine:
            await self._reply(update, "Engine not available")
            return
        lines = ["📊 Open Positions"]
        has_positions = False
        for sym, pos in self.engine.positions.items():
            if pos is None:
                continue
            has_positions = True
            side = "LONG" if pos.side == 1 else "SHORT"
            lines.append(
                f"{'🟢' if pos.side == 1 else '🔴'} {sym} {side}\n"
                f"Entry: ${pos.entry_price:.2f} | Qty: {pos.quantity:.6f}\n"
                f"SL: ${pos.sl_price:.2f} | TP: ${pos.tp_price:.2f}"
            )
        if not has_positions:
            lines.append("No open positions.")
        await self._reply(update, "\n\n".join(lines))

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        log_path = os.path.join(os.path.dirname(__file__), "logs", "bot.log")
        if not os.path.exists(log_path):
            await self._reply(update, "No log file found.")
            return
        try:
            with open(log_path, "r", encoding="utf-8", errors="backslashreplace") as f:
                lines = f.readlines()
            tail = lines[-50:]
            text = "".join(tail)
            if len(text) > 4000:
                text = "..." + text[-3997:]
            await self._reply(update, f"📋 Last {len(tail)} log lines:\n```\n{text}\n```")
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            await self._reply(update, f"Error reading logs: {e}")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return
        help_text = (
            "🤖 Available Commands\n\n"
            "/status — Bot status, equity, open trades\n"
            "/pause — Pause new entries (keep managing open trades)\n"
            "/resume — Resume new entries\n"
            "/stop — Stop bot (no new entries after current tick)\n"
            "/positions — List all open positions\n"
            "/logs — Show last 50 log lines\n"
            "/help — Show this message"
        )
        await self._reply(update, help_text)

    async def _handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip()
        routing = {
            "📊 Status": self._cmd_status,
            "⏸ Pause": self._cmd_pause,
            "▶ Resume": self._cmd_resume,
            "🛑 Stop": self._cmd_stop,
            "📋 Positions": self._cmd_positions,
            "📋 Logs": self._cmd_logs,
        }
        handler = routing.get(text)
        if handler:
            await handler(update, context)
        else:
            await self._reply(update, f"Unknown button: {text}\nUse the buttons below or /help.")

    def _is_authorized(self, update: Update) -> bool:
        if not self.chat_id:
            return False
        user_id = str(update.effective_user.id)
        if user_id != self.chat_id and str(update.effective_chat.id) != self.chat_id:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return False
        return True
