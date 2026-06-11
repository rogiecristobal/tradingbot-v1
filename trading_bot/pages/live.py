import streamlit as st
import json
import os
import subprocess
import time
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Live Bot Control", layout="wide")

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
LOG_PATH = BASE / "live" / "logs" / "bot.log"
ENV_PATH = BASE / ".env"


def _read_config():
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _read_log(tail=50):
    if not LOG_PATH.exists():
        return ""
    with open(LOG_PATH, "r", encoding="utf-8", errors="backslashreplace") as f:
        lines = f.readlines()
    return "".join(lines[-tail:])


def _bot_running():
    if "bot_proc" not in st.session_state or st.session_state.bot_proc is None:
        return False
    poll = st.session_state.bot_proc.poll()
    return poll is None


def start_bot():
    if _bot_running():
        return
    env = os.environ.copy()
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip("\"'")
    st.session_state.bot_proc = subprocess.Popen(
        ["python", "-m", "live.run"],
        cwd=str(BASE),
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def stop_bot():
    if not _bot_running():
        return
    st.session_state.bot_proc.terminate()
    try:
        st.session_state.bot_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        st.session_state.bot_proc.kill()
    st.session_state.bot_proc = None


if "bot_proc" not in st.session_state:
    st.session_state.bot_proc = None

st.title("Live Bot Control")

config = _read_config()

# ── Status bar ──
if config:
    mode = config.get("mode", "paper").upper()
    has_keys = bool(config.get("api_key") and config.get("api_secret"))
    sym_count = len(config.get("symbols", []))
    capital = config.get("capital", 0)
    positions_raw = config.get("positions", {})
    open_count = sum(1 for v in positions_raw.values() if v is not None)

    running = _bot_running()
    status_color = "#00ff88" if running else ("#ffaa00" if config else "#ff4444")
    status_text = "RUNNING" if running else ("STOPPED" if config else "NO CONFIG")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px;color:#888'>Status</div>"
                  f"<div style='font-size:22px;font-weight:700;color:{status_color}'>{status_text}</div></div>",
                  unsafe_allow_html=True)
    col2.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px;color:#888'>Mode</div>"
                  f"<div style='font-size:22px;font-weight:700'>{mode}</div></div>",
                  unsafe_allow_html=True)
    col3.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px;color:#888'>Symbols</div>"
                  f"<div style='font-size:22px;font-weight:700'>{sym_count}</div></div>",
                  unsafe_allow_html=True)
    col4.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px;color:#888'>Open Positions</div>"
                  f"<div style='font-size:22px;font-weight:700'>{open_count}</div></div>",
                  unsafe_allow_html=True)
    col5.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px;color:#888'>Capital</div>"
                  f"<div style='font-size:22px;font-weight:700'>${capital:.2f}</div></div>",
                  unsafe_allow_html=True)
else:
    st.warning("No config.json found. Run the bot once to create it, or create it manually.")

# ── Controls ──
st.subheader("Controls")
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)
with ctrl_col1:
    if _bot_running():
        if st.button("Stop Bot", type="primary", use_container_width=True):
            stop_bot()
            st.rerun()
    else:
        if st.button("Start Bot", type="primary", use_container_width=True):
            start_bot()
            st.rerun()

with ctrl_col2:
    if config and _bot_running():
        paused = config.get("_paused", False)
        if paused:
            if st.button("▶ Resume", use_container_width=True):
                config["_paused"] = False
                _save_config(config)
                st.rerun()
        else:
            if st.button("⏸ Pause", use_container_width=True):
                config["_paused"] = True
                _save_config(config)
                st.rerun()

with ctrl_col3:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Positions ──
if config:
    positions = config.get("positions", {})
    open_positions = {k: v for k, v in positions.items() if v is not None}
    if open_positions:
        st.subheader("Open Positions")
        rows = []
        for sym, pos in open_positions.items():
            rows.append({
                "Symbol": sym,
                "Side": "LONG" if pos["side"] == 1 else "SHORT",
                "Entry": f"${pos['entry_price']:.2f}",
                "Qty": f"{pos['quantity']:.6f}",
                "SL": f"${pos['sl_price']:.2f}",
                "TP": f"${pos['tp_price']:.2f}",
                "Entry Time": pos.get("entry_time", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Logs ──
st.subheader("Logs")
log_text = _read_log(100)
st.text_area("Last 100 lines", log_text, height=300, disabled=True)

option = st.selectbox("Show more lines", [50, 100, 200, 500], index=1)
if st.button("Refresh Logs"):
    log_text = _read_log(option)
    st.text_area("Last logs", log_text, height=300, disabled=True)

# ── Config editor ──
if config:
    st.subheader("Config Editor")
    with st.expander("Edit config.json", expanded=False):
        config_json = json.dumps(config, indent=2)
        edited = st.text_area("config.json", config_json, height=400)
        if st.button("Save Config"):
            try:
                parsed = json.loads(edited)
                _save_config(parsed)
                st.success("Config saved! Restart bot if running.")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")
