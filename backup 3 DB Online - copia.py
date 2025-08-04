import streamlit as st
import re
from datetime import datetime, date
import pytz
from pytz import timezone
import psycopg2
import psycopg2.extras
import json

# Optional editors
try:
    from streamlit_quill import st_quill
    HAS_QUILL = True
except ImportError:
    HAS_QUILL = False

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

# Neon DB connection\ nPG_CONN = {
    "dbname":   "neondb",
    "user":     "neondb_owner",
    "password": "npg_RpJPZ5dGLhm9",
    "host":     "ep-tiny-voice-afh7l7cf-pooler.c-2.us-west-2.aws.neon.tech",
    "port":     "5432",
    "sslmode":  "require"
}

# UI constants
CATEGORIES = ["Feedback", "Pending", "Question", "Request", "Other", "Update"]
ICONS = {"Feedback": "💬", "Pending": "⏳", "Question": "❓", "Request": "📥", "Other": "🔹", "Update": "🔄"}
USERS           = ["Aldo", "Moni"]
ADMIN_PASSWORD  = "Pa27Ma15"
CATEGORY_COLORS = {
    "Question": "#2979FF", "Pending": "#FF9800",
    "Update":   "#009688", "Request": "#8E24AA",
    "Feedback": "#43A047", "Other": "#546E7A"
}
USER_COLORS = {"Aldo": "#23c053", "Moni": "#e754c5"}

# Helpers

def get_pg_conn():
    return psycopg2.connect(**PG_CONN)

def format_datetime_pst(dt):
    la = timezone("America/Los_Angeles")
    return dt.astimezone(la).strftime("%d %b %Y - %I:%M %p") + " PST"

def colored_name(user):
    col = USER_COLORS.get(user, "#000")
    return f'<span style="color:{col};font-weight:bold">{user}</span>'

def category_label(cat):
    icon = ICONS.get(cat, "")
    col  = CATEGORY_COLORS.get(cat, "#888")
    return (
        f'<span style="background:{col};color:#fff;'
        f'padding:2px 6px;border-radius:4px;font-size:0.95em">'
        f'{icon} {cat}</span>'
    )

def strip_empty_paragraphs(html: str) -> str:
    return re.sub(r'(?i)<p>(?:\s|<br\s*/?>)*</p>', '', html).strip()

def load_entries():
    with get_pg_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM logger_entries ORDER BY id DESC")
            rows = cur.fetchall()
    return [{
        "id":       r["id"],
        "user":     r["user_name"],
        "category": r["category"],
        "comment":  r["comment"],
        "datetime": r["datetime"],
        "replies":  r["replies"] or [],
        "closed":   r["closed"]
    } for r in rows]

def save_entries(entries):
    with get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM logger_entries")
            for e in entries:
                cur.execute(
                    """
                    INSERT INTO logger_entries
                      (user_name, category, comment, datetime, replies, closed)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        e["user"], e["category"], e["comment"], e["datetime"],
                        json.dumps(e.get("replies", [])),
                        e.get("closed", False)
                    )
                )
        conn.commit()

def get_entry_date(e):
    try:
        d = e["datetime"].split(" - ")[0]
        return datetime.strptime(d, "%d %b %Y").date()
    except:
        return None

# Callbacks with dynamic editor key

def add_comment_callback(editor_key):
    raw = st.session_state.get(editor_key, "")
    cleaned = strip_empty_paragraphs(raw)
    if cleaned:
        st.session_state.entries.insert(0, {
            "user":     st.session_state.current_user,
            "category": st.session_state.new_category,
            "comment":  cleaned,
            "datetime": format_datetime_pst(datetime.now(pytz.utc)),
            "replies":  [],
            "closed":   False
        })
        save_entries(st.session_state.entries)
    # bump editor to reset
    st.session_state.editor_version += 1


def clear_comment_callback(editor_key):
    st.session_state.editor_version += 1


def close_entry_callback(idx):
    st.session_state.entries[idx]["closed"] = True
    save_entries(st.session_state.entries)


def send_reply_callback(idx):
    key = f"reply_content_{idx}"
    raw = st.session_state.get(key, "")
    cleaned = strip_empty_paragraphs(raw)
    if cleaned:
        st.session_state.entries[idx]["replies"].append({
            "user":     st.session_state.current_user,
            "comment":  cleaned,
            "datetime": format_datetime_pst(datetime.now(pytz.utc))
        })
        save_entries(st.session_state.entries)
    st.session_state.active_reply = None
    st.session_state[key] = ""


def delete_all_callback():
    if st.session_state.admin_pwd == ADMIN_PASSWORD:
        st.session_state.entries = []
        save_entries([])
        st.sidebar.success("All entries deleted.")
    else:
        st.sidebar.error("Invalid password")


def delete_by_date_callback():
    if st.session_state.admin_pwd == ADMIN_PASSWORD and st.session_state.del_date:
        before = len(st.session_state.entries)
        st.session_state.entries = [
            e for e in st.session_state.entries
            if get_entry_date(e) != st.session_state.del_date
        ]
        save_entries(st.session_state.entries)
        st.sidebar.success(f"Deleted {before - len(st.session_state.entries)} on {st.session_state.del_date}")
    else:
        st.sidebar.error("Invalid password or date")

# Main

def main():
    st.set_page_config(page_title="Logger", layout="wide")

    # init editor_version
    if "editor_version" not in st.session_state:
        st.session_state.editor_version = 0

    # defaults
    defaults = {
        "entries":        load_entries(),
        "current_user":   USERS[0],
        "new_category":   CATEGORIES[0],
        "filter_use_date": True,
        "filter_date":    date.today(),
        "filter_keyword": "",
        "filter_open":    False,
        "active_reply":   None,
        "admin_pwd":      "",
        "del_date":       None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Sidebar
    st.sidebar.header("User")
    st.sidebar.radio("Select user:", USERS, key="current_user")
    st.sidebar.markdown("---")

    st.sidebar.header("Filter")
    st.sidebar.checkbox("Filter by date", key="filter_use_date")
    all_dates = sorted(
        {d for e in st.session_state.entries if (d := get_entry_date(e))},
        reverse=True
    )
    date_input_args = {
        "label": "Date",
        "value": st.session_state.filter_date,
        "min_value": (all_dates[-1] if all_dates else None),
        "max_value": (all_dates[0]  if all_dates else None),
        "key": "filter_date"
    }
    if not st.session_state.filter_use_date:
        date_input_args["disabled"] = True
    st.sidebar.date_input(**date_input_args)
    st.sidebar.text_input("Search", "", key="filter_keyword")
    st.sidebar.checkbox("Show open only", key="filter_open")
    st.sidebar.markdown("---")

    st.sidebar.subheader("Admin: Delete")
    st.sidebar.text_input("Password", type="password", key="admin_pwd")
    st.sidebar.button("Delete ALL", on_click=delete_all_callback)
    st.sidebar.date_input("Delete date", key="del_date")
    st.sidebar.button("Delete on date", on_click=delete_by_date_callback)

    # Main header
    user = st.session_state.current_user
    st.markdown(
        f"<h1 style='text-align:center;color:{USER_COLORS[user]}'>{user}</h1>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    # New comment form
    st.subheader("Add a new comment")
    st.selectbox(
        "Category",
        CATEGORIES,
        format_func=lambda c: f"{ICONS[c]} {c}",
        key="new_category"
    )

    # dynamic editor key
    editor_key = f"new_content_{st.session_state.editor_version}"
    if HAS_QUILL:
        st_quill(html=True, key=editor_key)
    elif HAS_ACE:
        st_ace(language="html", theme="monokai", key=editor_key, height=200)
    else:
        st.text_area("Comment", key=editor_key, height=200)

    # buttons side-by-side
    c1, c2 = st.columns(2)
    with c1:
        st.button("Add comment", on_click=add_comment_callback, args=(editor_key,))
    with c2:
        st.button("Clear comment", on_click=clear_comment_callback, args=(editor_key,))

    # display entries
    filtered = []
    for idx, e in enumerate(st.session_state.entries):
        if st.session_state.filter_use_date and get_entry_date(e) != st.session_state.filter_date:
            continue
        if st.session_state.filter_open and e["closed"]:
            continue
        kw = st.session_state.filter_keyword.lower()
        if kw and kw not in e["comment"].lower():
            continue
        filtered.append((idx, e))

    if filtered:
        st.markdown("## Entries")
        for i, (idx, e) in enumerate(filtered):
            if i > 0:
                st.divider()
            st.markdown(
                f"{colored_name(e['user'])} {category_label(e['category'])} — <em>{e['datetime']}</em>",
                unsafe_allow_html=True
            )
            if not e["closed"]:
                st.button("Close", key=f"close_{idx}", on_click=close_entry_callback, args=(idx,))
            else:
                st.markdown("**Closed**")
            st.markdown(e["comment"], unsafe_allow_html=True)
            for r in e.get("replies", []):
                st.markdown(
                    f"> **{r['user']}** — {r['datetime']}\n> {r['comment']}",
                    unsafe_allow_html=True
                )
            if not e["closed"]:
                st.button("Reply", key=f"reply_btn_{idx}", on_click=lambda i=idx: st.session_state.__setitem__("active_reply", i))
            if not e["closed"] and st.session_state.active_reply == idx:
                reply_key = f"reply_content_{idx}"
                if HAS_QUILL:
                    st_quill(html=True, key=reply_key)
                elif HAS_ACE:
                    st_ace(language="html", theme="monokai", key=reply_key, height=150)
                else:
                    st.text_area("Your reply", key=reply_key, height=150)
                st.button("Send reply", key=f"send_rep_{idx}", on_click=send_reply_callback, args=(idx,))

if __name__ == "__main__":
    main()
