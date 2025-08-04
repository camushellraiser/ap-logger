import streamlit as st
import re
from datetime import datetime, date
import pytz
from pytz import timezone
import psycopg2
import psycopg2.extras
import json

try:
    from streamlit_quill import st_quill
    has_quill = True
except ImportError:
    has_quill = False

try:
    from streamlit_ace import st_ace
    has_ace = True
except ImportError:
    has_ace = False

# --- DB connection ---
PG_CONN = {
    "dbname":"neondb","user":"neondb_owner","password":"npg_RpJPZ5dGLhm9",
    "host":"ep-tiny-voice-afh7l7cf-pooler.c-2.us-west-2.aws.neon.tech",
    "port":"5432","sslmode":"require"
}

CATEGORIES = ["Feedback","Pending","Question","Request","Other","Update"]
ICONS      = {"Feedback":"💬","Pending":"⏳","Question":"❓","Request":"📥","Other":"🔹","Update":"🔄"}
USERS      = ["Aldo","Moni"]
ADMIN_PWD  = "Pa27Ma15"
CATEGORY_COLORS = {
    "Question":"#2979FF","Pending":"#FF9800","Update":"#009688",
    "Request":"#8E24AA","Feedback":"#43A047","Other":"#546E7A"
}
USER_COLORS = {"Aldo":"#23c053","Moni":"#e754c5"}

def get_pg_conn():
    return psycopg2.connect(**PG_CONN)

def format_datetime_pst(dt):
    la = timezone("America/Los_Angeles")
    return dt.astimezone(la).strftime("%d %b %Y - %I:%M %p") + " PST"

def strip_empty_paragraphs(html: str) -> str:
    return re.sub(r'(?i)<p>(?:\s|<br\s*/?>)*</p>', '', html).strip()

def load_entries():
    with get_pg_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
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
    with get_pg_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM logger_entries")
        for e in entries:
            cur.execute(
                """INSERT INTO logger_entries
                   (user_name,category,comment,datetime,replies,closed)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    e["user"],e["category"],e["comment"],e["datetime"],
                    json.dumps(e["replies"]),e["closed"]
                )
            )
        conn.commit()

def get_entry_date(e):
    try:
        d = e["datetime"].split(" - ")[0]
        return datetime.strptime(d, "%d %b %Y").date()
    except:
        return None

# — editor key-bumping
def bump_editor():
    st.session_state.editor_count += 1
    key = f"new_content_{st.session_state.editor_count}"
    st.session_state.editor_key = key
    st.session_state[key] = ""
    st.session_state.new_content_content = ""

def add_comment_callback():
    raw = st.session_state.new_content_content or ""
    content = strip_empty_paragraphs(raw)
    if content:
        st.session_state.entries.insert(0, {
            "user":     st.session_state.current_user,
            "category": st.session_state.new_category,
            "comment":  content,
            "datetime": format_datetime_pst(datetime.now(pytz.utc)),
            "replies":  [], "closed": False
        })
        save_entries(st.session_state.entries)
    bump_editor()

def clear_comment_callback():
    bump_editor()

def close_entry_callback(idx):
    st.session_state.entries[idx]["closed"] = True
    save_entries(st.session_state.entries)

def send_reply_callback(idx):
    key = f"reply_content_{idx}"
    raw = st.session_state.get(key, "") or ""
    content = strip_empty_paragraphs(raw)
    if content:
        st.session_state.entries[idx]["replies"].append({
            "user": st.session_state.current_user,
            "comment": content,
            "datetime": format_datetime_pst(datetime.now(pytz.utc))
        })
        save_entries(st.session_state.entries)
    st.session_state.active_reply = None
    st.session_state[key] = ""

def delete_all_callback():
    if st.session_state.admin_pwd == ADMIN_PWD:
        st.session_state.entries = []
        save_entries([])
        st.sidebar.success("All entries deleted.")
    else:
        st.sidebar.error("Invalid password")

def delete_by_date_callback():
    if st.session_state.admin_pwd == ADMIN_PWD and st.session_state.del_date:
        before = len(st.session_state.entries)
        st.session_state.entries = [
            e for e in st.session_state.entries
            if get_entry_date(e) != st.session_state.del_date
        ]
        save_entries(st.session_state.entries)
        st.sidebar.success(f"Deleted {before-len(st.session_state.entries)} entries on {st.session_state.del_date}")
    else:
        st.sidebar.error("Invalid password or date")

# — main
def main():
    st.set_page_config(page_title="Logger", layout="wide")

    # --- init session state ---
    defaults = {
        "entries":        load_entries(),
        "current_user":   USERS[0],
        "new_category":   CATEGORIES[0],
        "filter_date":    date.today(),
        "filter_keyword": "",
        "filter_open":    False,
        "active_reply":   None,
        "admin_pwd":      "",
        "del_date":       None,
        # editor state:
        "editor_count":          0,
        "editor_key":            "new_content_0",
        "new_content_content":   ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # --- Sidebar ---
    st.sidebar.header("User")
    st.sidebar.radio("Select user:", USERS, key="current_user")
    st.sidebar.markdown("---")
    st.sidebar.header("Filter")
    all_dates = sorted(
        {d for e in st.session_state.entries if (d:=get_entry_date(e))},
        reverse=True
    )
    st.sidebar.date_input(
        "Date",
        value=st.session_state.filter_date,
        min_value=(all_dates[-1] if all_dates else None),
        max_value=(all_dates[0]  if all_dates else None),
        key="filter_date"
    )
    st.sidebar.text_input("Search", "", key="filter_keyword")
    st.sidebar.checkbox("Show open only", key="filter_open")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Admin: Delete")
    st.sidebar.text_input("Password", type="password", key="admin_pwd")
    st.sidebar.button("Delete ALL", on_click=delete_all_callback)
    st.sidebar.date_input("Delete date", key="del_date")
    st.sidebar.button("Delete on date", on_click=delete_by_date_callback)

    # --- Header ---
    user = st.session_state.current_user
    st.markdown(
        f"<h1 style='text-align:center;color:{USER_COLORS[user]}'>{user}</h1>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    # --- New comment form ---
    st.subheader("Add a new comment")
    st.selectbox(
        "Category",
        CATEGORIES,
        format_func=lambda c: f"{ICONS[c]} {c}",
        key="new_category"
    )

    # use the bumped key + sync back into new_content_content
    key = st.session_state.editor_key
    if has_quill:
        st_quill(value=st.session_state.new_content_content, html=True, key=key)
    elif has_ace:
        st_ace(
            value=st.session_state.new_content_content,
            language="html", theme="monokai",
            key=key, height=200
        )
    else:
        st.text_area("Comment", height=200, key=key)

    # after rendering, sync into our stable variable
    st.session_state.new_content_content = st.session_state.get(key, "")

    # buttons side-by-side
    c1, c2 = st.columns(2)
    with c1:
        st.button("Add comment", on_click=add_comment_callback)
    with c2:
        st.button("Clear comment", on_click=clear_comment_callback)

    # --- display entries ---
    filtered = []
    for idx, e in enumerate(st.session_state.entries):
        if get_entry_date(e) != st.session_state.filter_date:
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
            if i>0: st.divider()
            st.markdown(
                f"<span style='color:{USER_COLORS[e['user']]};font-weight:bold'>{e['user']}</span> "
                f"{category_label(e['category'])} — <em>{e['datetime']}</em>",
                unsafe_allow_html=True
            )
            if not e["closed"]:
                st.button("Close", key=f"close_{idx}",
                          on_click=close_entry_callback, args=(idx,))
            else:
                st.markdown("**Closed**")
            st.markdown(e["comment"], unsafe_allow_html=True)
            for r in e["replies"]:
                st.markdown(
                    f"> **{r['user']}** — {r['datetime']}\n> {r['comment']}",
                    unsafe_allow_html=True
                )
            if not e["closed"]:
                st.button("Reply", key=f"reply_btn_{idx}",
                          on_click=lambda i=idx: st.session_state.__setitem__("active_reply", i))
            if not e["closed"] and st.session_state.active_reply==idx:
                rk = f"reply_content_{idx}"
                if has_quill:
                    st_quill(value=st.session_state.get(rk,""), html=True, key=rk)
                elif has_ace:
                    st_ace(value=st.session_state.get(rk,""),
                           language="html",theme="monokai",key=rk,height=150)
                else:
                    st.text_area("Your reply", key=rk, height=150)
                st.button("Send reply", key=f"send_rep_{idx}",
                          on_click=send_reply_callback, args=(idx,))

if __name__ == "__main__":
    main()
