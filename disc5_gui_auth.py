# disc5_gui_auth.py
# Local login, roles and activity audit for the DISC5 Re-ID app (air-gapped, stdlib only).
#
# Scope and honest framing (state this in the manual, not just here):
#   The app runs as a local process whose state files sit beside the executable. Anyone with
#   access to that Windows account can read, edit or delete users.json exactly as they can
#   gallery.npz. This gate is an ACCOUNTABILITY and MISTAKE-PREVENTION control -- it puts a
#   name against every enrolment and deletion and stops an Operator casually clearing the
#   gallery. It is NOT a security boundary against a determined local user. The real access
#   boundary is the Windows account on the PC.
#   Passwords are scrypt-hashed for one concrete reason: so one user cannot read another's
#   password out of a file they can already open. People reuse passwords on systems that are
#   not air-gapped.
#
# Design notes:
#   - stdlib ONLY (hashlib/secrets/json/csv/datetime). No new PyInstaller dependency, no
#     offline wheel to ship.
#   - NODPAC runs a SINGLE shared Windows account, so the in-app credential is the only thing
#     distinguishing users. Hence: idle timeout, explicit logout, and the current user shown
#     permanently -- otherwise the audit log records the wrong person, which is worse than no
#     audit log at all.
#   - actor_identity() is the single seam for a future switch to Windows-account identity
#     (one function to change if a site ever gives each user their own Windows login).
#   - audit_log.jsonl is a SEPARATE file from users.json. The documented recovery path
#     (delete users.json -> app returns to first-run) is available to everyone on that PC;
#     keeping the log separate means a credential reset shows up as a gap plus a fresh
#     bootstrap event rather than erasing the history.
#
# Files written beside the executable (app_dir):
#   users.json       {"version":1,"users":{name:{role,salt,hash,params,must_change,disabled,...}}}
#   audit_log.jsonl  append-only, one JSON object per line
#
# Public API used by disc5_gui_app.py:
#   require_login(app_dir) -> user dict            gate; renders login/bootstrap UI and st.stop()s
#   is_analyst(user) / require_role(user, role)    role checks
#   audit(app_dir, user, action, obj="", outcome="ok", **extra)
#   render_sidebar_identity(app_dir, user)         who-am-I + logout + idle countdown
#   render_users_tab(app_dir, user)                Admin-only user administration
#   render_activity_tab(app_dir, user)             Admin-only audit viewer + CSV export

import os, io, csv, json, time, base64, hashlib, secrets, datetime, getpass
import streamlit as st

# --------------------------------------------------------------------------- policy (edit here)
# These five constants are the entire password policy surface. If NODPAC states a naval IT
# standard, it is applied by editing this block -- no other code changes.
MIN_PASSWORD_LEN = 8            # no complexity rules by default: they produce sticky notes
REQUIRE_COMPLEXITY = False      # True -> require 3 of {lower, upper, digit, symbol}
PASSWORD_EXPIRY_DAYS = 0        # 0 = never expires; >0 forces a change at first login past age
IDLE_TIMEOUT_MIN = 20           # shared Windows account -> unattended session must expire
MAX_FAILED_LOGINS = 5           # then a short lockout (an audit event either way)
LOCKOUT_MINUTES = 5
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
ROLES = ("Admin", "Analyst", "Operator")   # strictly nested: Operator < Analyst < Admin
_ROLE_RANK = {"Operator": 0, "Analyst": 1, "Admin": 2}

USERS_FILE = "users.json"
AUDIT_FILE = "audit_log.jsonl"


# --------------------------------------------------------------------------- small helpers
def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def actor_identity():
    """Host-level identity recorded alongside the in-app user.

    THE SEAM: at NODPAC every person shares one Windows account, so this is the same string
    for everybody and carries no distinguishing information -- it is logged for completeness
    only. If a site ever issues per-user Windows accounts, this function becomes the identity
    source and the credential store can be reduced to a role map."""
    try:
        return getpass.getuser()
    except Exception:
        return "(unknown)"


def _users_path(app_dir):
    return os.path.join(app_dir, USERS_FILE)


def _audit_path(app_dir):
    return os.path.join(app_dir, AUDIT_FILE)


def _atomic_write(path, text):
    """Write via temp + os.replace so an interrupted save cannot truncate the user store."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------------- password hashing
def hash_password(password, salt=None):
    """scrypt hash -> (salt_b64, hash_b64, params dict). Stdlib; no external dependency."""
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return (base64.b64encode(salt).decode(), base64.b64encode(dk).decode(),
            dict(kdf="scrypt", n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32))


def verify_password(password, rec):
    """Constant-time verification against a stored user record."""
    try:
        p = rec.get("params") or {}
        salt = base64.b64decode(rec["salt"])
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=int(p.get("n", SCRYPT_N)), r=int(p.get("r", SCRYPT_R)),
                            p=int(p.get("p", SCRYPT_P)), dklen=int(p.get("dklen", 32)))
        return secrets.compare_digest(base64.b64encode(dk).decode(), rec["hash"])
    except Exception:
        return False


def password_problem(pw, pw2=None):
    """Return a human message if the proposed password is unacceptable, else None."""
    if len(pw or "") < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if REQUIRE_COMPLEXITY:
        classes = sum([any(c.islower() for c in pw), any(c.isupper() for c in pw),
                       any(c.isdigit() for c in pw),
                       any(not c.isalnum() for c in pw)])
        if classes < 3:
            return ("Password must use at least three of: lower case, upper case, "
                    "digits, symbols.")
    if pw2 is not None and pw != pw2:
        return "The two passwords do not match."
    return None


def password_expired(rec):
    """True if PASSWORD_EXPIRY_DAYS is in force and this password is older than that.
    Records written before expiry was enabled have no `pw_set` and are treated as current
    until their next change, so enabling the policy never locks anyone out retroactively."""
    if PASSWORD_EXPIRY_DAYS <= 0 or not rec.get("pw_set"):
        return False
    try:
        age = datetime.datetime.now() - datetime.datetime.fromisoformat(rec["pw_set"])
    except Exception:
        return False
    return age.days >= PASSWORD_EXPIRY_DAYS


# --------------------------------------------------------------------------- user store
def load_users(app_dir):
    p = _users_path(app_dir)
    if not os.path.exists(p):
        return {"version": 1, "users": {}}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("users", {})
        return d
    except Exception:
        # A corrupt store must not lock the app into a crash loop; surface it and allow
        # the documented recovery (delete users.json -> first-run bootstrap).
        st.error(f"{USERS_FILE} is unreadable or corrupt. Delete it beside the executable to "
                 f"return the app to first-run setup. The gallery is not affected.")
        st.stop()


def save_users(app_dir, data):
    _atomic_write(_users_path(app_dir), json.dumps(data, indent=2, sort_keys=True))


def create_user(app_dir, name, password, role, must_change=True, created_by=""):
    """Add a user. Returns (ok, message)."""
    name = (name or "").strip()
    if not name:
        return False, "Username is required."
    if role not in ROLES:
        return False, f"Role must be one of {', '.join(ROLES)}."
    msg = password_problem(password)
    if msg:
        return False, msg
    d = load_users(app_dir)
    if name.lower() in {u.lower() for u in d["users"]}:
        return False, f"User '{name}' already exists."
    salt, h, params = hash_password(password)
    d["users"][name] = dict(role=role, salt=salt, hash=h, params=params,
                            must_change=bool(must_change), disabled=False,
                            created=_now_iso(), created_by=created_by, pw_set=_now_iso(),
                            last_login="", failed=0, locked_until="")
    save_users(app_dir, d)
    return True, f"Created {role} '{name}'."


def set_password(app_dir, name, password, must_change=False):
    d = load_users(app_dir)
    if name not in d["users"]:
        return False, "No such user."
    msg = password_problem(password)
    if msg:
        return False, msg
    salt, h, params = hash_password(password)
    d["users"][name].update(salt=salt, hash=h, params=params, pw_set=_now_iso(),
                            must_change=bool(must_change), failed=0, locked_until="")
    save_users(app_dir, d)
    return True, f"Password updated for '{name}'."


def _enabled_admins(users, excluding=None):
    return [n for n, r in users.items()
            if r.get("role") == "Admin" and not r.get("disabled") and n != excluding]


def update_user(app_dir, name, role=None, disabled=None):
    """Change role and/or enabled state, guarding the last enabled Analyst."""
    d = load_users(app_dir)
    if name not in d["users"]:
        return False, "No such user."
    rec = d["users"][name]
    losing_admin = (rec.get("role") == "Admin" and not rec.get("disabled")
                    and ((role is not None and role != "Admin") or disabled is True))
    if losing_admin and not _enabled_admins(d["users"], excluding=name):
        return False, "This is the last enabled Admin — demoting or disabling it would lock " \
                      "everyone out of user administration."
    if role is not None:
        rec["role"] = role
    if disabled is not None:
        rec["disabled"] = bool(disabled)
    save_users(app_dir, d)
    return True, f"Updated '{name}'."


def delete_user(app_dir, name):
    d = load_users(app_dir)
    if name not in d["users"]:
        return False, "No such user."
    rec = d["users"][name]
    if rec.get("role") == "Admin" and not rec.get("disabled") \
            and not _enabled_admins(d["users"], excluding=name):
        return False, "This is the last enabled Admin — deleting it would lock everyone out."
    del d["users"][name]
    save_users(app_dir, d)
    return True, f"Deleted '{name}'."


# --------------------------------------------------------------------------- audit log
def audit(app_dir, user, action, obj="", outcome="ok", **extra):
    """Append one event. Never raises: a failed log write must not break the operator's task.

    Timestamps come from the local clock, which on an air-gapped machine has no NTP and will
    drift -- the install step should verify date/time, and a corrected clock is worth logging."""
    rec = dict(ts=_now_iso(), user=(user or {}).get("name", "(none)"),
               role=(user or {}).get("role", ""), host_account=actor_identity(),
               action=action, object=str(obj), outcome=outcome)
    rec.update({k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                for k, v in extra.items()})
    try:
        with open(_audit_path(app_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
    except Exception:
        pass
    # Real work counts as activity. Without this a single long script run (e.g. a bulk enrol
    # exceeding IDLE_TIMEOUT_MIN) would be treated as idleness and sign the user out the
    # moment it finished. Only genuine inactivity should expire a session.
    try:
        _touch_session()
    except Exception:
        pass


def read_audit(app_dir, limit=2000):
    """Most recent `limit` events, newest first. Tolerates partial final lines."""
    p = _audit_path(app_dir)
    if not os.path.exists(p):
        return []
    out = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out[-limit:][::-1]


def audit_csv(events):
    cols = ["ts", "user", "role", "host_account", "action", "object", "outcome", "detail"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for e in events:
        # 'detail' is a named column; anything else the caller passed is folded in beside it.
        extra = {k: v for k, v in e.items() if k not in cols}
        detail = "; ".join(([str(e["detail"])] if e.get("detail") else [])
                           + [f"{k}={v}" for k, v in sorted(extra.items())])
        w.writerow([e.get(c, "") for c in cols[:-1]] + [detail])
    return buf.getvalue()


# --------------------------------------------------------------------------- session / roles
def has_role(user, role):
    """Nested check: an Admin passes every check, an Analyst passes Analyst+Operator checks."""
    return bool(user) and _ROLE_RANK.get(user.get("role"), -1) >= _ROLE_RANK[role]


def is_admin(user):
    return has_role(user, "Admin")


def is_analyst(user):
    return has_role(user, "Analyst")


def require_role(user, role):
    """Guard for any code path that must not run for the wrong role."""
    if not has_role(user, role):
        st.error("Your role does not permit this action.")
        st.stop()


def _touch_session():
    st.session_state["auth_last_seen"] = time.time()


def _session_expired():
    last = st.session_state.get("auth_last_seen")
    return bool(last) and (time.time() - last) > IDLE_TIMEOUT_MIN * 60


def logout(app_dir, reason="logout"):
    user = st.session_state.get("auth_user")
    if user:
        audit(app_dir, user, reason, outcome="ok")
    for k in ("auth_user", "auth_last_seen"):
        st.session_state.pop(k, None)
    st.session_state.pop("qres", None)      # never leave one user's query on screen for the next


def _locked_out(rec):
    lu = rec.get("locked_until") or ""
    if not lu:
        return 0
    try:
        left = (datetime.datetime.fromisoformat(lu) - datetime.datetime.now()).total_seconds()
    except Exception:
        return 0
    return max(0, int(left // 60) + 1) if left > 0 else 0


def _attempt_login(app_dir, name, password):
    """Returns (user_dict_or_None, message). Records the attempt in the audit log."""
    d = load_users(app_dir)
    # Case-insensitive match so 'Anupam' and 'anupam' are the same person.
    real = next((u for u in d["users"] if u.lower() == (name or "").strip().lower()), None)
    if real is None:
        audit(app_dir, {"name": name or "(blank)", "role": ""}, "login", name, "fail_no_user")
        return None, "Unknown username or wrong password."
    rec = d["users"][real]
    if rec.get("disabled"):
        audit(app_dir, {"name": real, "role": rec.get("role", "")}, "login", real, "fail_disabled")
        return None, "This account is disabled. Ask an Analyst to re-enable it."
    mins = _locked_out(rec)
    if mins:
        return None, f"Too many failed attempts. Try again in about {mins} minute(s)."
    if not verify_password(password or "", rec):
        rec["failed"] = int(rec.get("failed", 0)) + 1
        if rec["failed"] >= MAX_FAILED_LOGINS:
            rec["locked_until"] = (datetime.datetime.now() +
                                   datetime.timedelta(minutes=LOCKOUT_MINUTES)).isoformat(
                                       timespec="seconds")
            rec["failed"] = 0
            save_users(app_dir, d)
            audit(app_dir, {"name": real, "role": rec.get("role", "")}, "login", real, "lockout")
            return None, f"Too many failed attempts. Locked for {LOCKOUT_MINUTES} minutes."
        save_users(app_dir, d)
        audit(app_dir, {"name": real, "role": rec.get("role", "")}, "login", real, "fail_password")
        return None, "Unknown username or wrong password."
    rec["failed"] = 0
    rec["locked_until"] = ""
    rec["last_login"] = _now_iso()
    save_users(app_dir, d)
    expired = password_expired(rec)
    user = dict(name=real, role=rec.get("role", "Operator"),
                must_change=bool(rec.get("must_change")) or expired)
    audit(app_dir, user, "login", real, "ok",
          **({"detail": "password expired, change forced"} if expired else {}))
    return user, ""


# --------------------------------------------------------------------------- UI: gate
def _render_bootstrap(app_dir):
    """First run: no users.json. Create the first Analyst. Role is forced, not chosen."""
    st.subheader("First-run setup")
    st.write("No user accounts exist yet. Create the first **Admin** account — the Admin "
             "then creates Analyst and Operator accounts from the **Users** tab.")
    st.caption("This login records who enrolled, deleted or queried what. It is not a "
               "substitute for controlling access to this PC.")
    n = st.text_input("Admin username", key="bs_name")
    p1 = st.text_input("Password", type="password", key="bs_p1")
    p2 = st.text_input("Confirm password", type="password", key="bs_p2")
    st.caption(f"Minimum {MIN_PASSWORD_LEN} characters.")
    if st.button("Create Admin account", type="primary"):
        msg = password_problem(p1, p2)
        if msg:
            st.error(msg)
            return
        ok, m = create_user(app_dir, n, p1, "Admin", must_change=False, created_by="(first run)")
        if not ok:
            st.error(m)
            return
        audit(app_dir, {"name": n.strip(), "role": "Admin"}, "bootstrap_admin", n.strip())
        st.success(m + " Sign in with it now.")
        st.rerun()


def _render_change_password(app_dir, user):
    """Forced on first login of an Analyst-created account, so the Analyst never knows an
    Operator's working password."""
    st.subheader("Set your password")
    st.write(f"Signed in as **{user['name']}** ({user['role']}). "
             "This account still uses the password an Analyst set for it — choose your own now.")
    p1 = st.text_input("New password", type="password", key="cp_p1")
    p2 = st.text_input("Confirm new password", type="password", key="cp_p2")
    st.caption(f"Minimum {MIN_PASSWORD_LEN} characters.")
    if st.button("Set password", type="primary"):
        msg = password_problem(p1, p2)
        if msg:
            st.error(msg)
            return
        ok, m = set_password(app_dir, user["name"], p1, must_change=False)
        if not ok:
            st.error(m)
            return
        user["must_change"] = False
        st.session_state["auth_user"] = user
        audit(app_dir, user, "password_change_self", user["name"])
        st.success("Password set.")
        st.rerun()


def require_login(app_dir):
    """The gate. Returns the signed-in user dict, or renders the login UI and stops the script.

    Call this immediately after st.set_page_config / st.title and before anything that reads
    or writes the gallery."""
    if not os.path.exists(_users_path(app_dir)):
        _render_bootstrap(app_dir)
        st.stop()

    user = st.session_state.get("auth_user")
    if user and _session_expired():
        logout(app_dir, reason="session_timeout")
        user = None
        st.warning(f"Signed out after {IDLE_TIMEOUT_MIN} minutes of inactivity.")

    if not user:
        st.subheader("Sign in")
        st.caption("This PC uses one shared Windows account, so sign in with your own name — "
                   "the activity log records what is done under it.")
        n = st.text_input("Username", key="li_name")
        p = st.text_input("Password", type="password", key="li_pass")
        if st.button("Sign in", type="primary"):
            u, msg = _attempt_login(app_dir, n, p)
            if u is None:
                st.error(msg)
            else:
                st.session_state["auth_user"] = u
                _touch_session()
                st.rerun()
        st.stop()

    if user.get("must_change"):
        _render_change_password(app_dir, user)
        st.stop()

    _touch_session()
    return user


# --------------------------------------------------------------------------- UI: sidebar
def render_sidebar_identity(app_dir, user):
    """Who am I, what can I do, and an explicit way out. Essential on a shared Windows account:
    without it the next person at the desk acts under the previous person's name."""
    st.markdown(f"**Signed in:** {user['name']}  \n**Role:** {user['role']}")
    if user.get("role") == "Operator":
        st.caption("Operator — identify and export your own query results. Enrolment, deletion "
                   "and gallery-wide exports are Analyst functions.")
    elif user.get("role") == "Analyst":
        st.caption("Analyst — all gallery functions. User accounts and the activity log are "
                   "Admin functions.")
    left = IDLE_TIMEOUT_MIN * 60 - (time.time() - st.session_state.get("auth_last_seen", time.time()))
    st.caption(f"Session ends after {IDLE_TIMEOUT_MIN} min idle (~{max(0, int(left // 60))} min left).")
    if st.button("Log out", use_container_width=True):
        logout(app_dir)
        st.rerun()


# --------------------------------------------------------------------------- UI: Analyst tabs
def render_users_tab(app_dir, user):
    require_role(user, "Admin")
    d = load_users(app_dir)
    users = d["users"]

    st.subheader("User accounts")
    st.caption("Roles are nested: Admin can do everything an Analyst can; an Analyst everything an "
               "Operator can. Accounts are stored beside the application in `users.json`, hashed with scrypt. "
               "Anyone with access to this PC can delete that file, which returns the app to "
               "first-run setup — the gallery is unaffected. Access to the PC itself is the "
               "real control.")
    # NOTE: an old two-role users.json (no Admin) has no way to reach this tab; delete it to re-bootstrap.

    rows = ["| user | role | status | created | last sign-in |", "|---|---|---|---|---|"]
    for n in sorted(users, key=str.lower):
        r = users[n]
        status = "disabled" if r.get("disabled") else ("must change password"
                                                       if r.get("must_change") else "active")
        rows.append(f"| {n} | {r.get('role','')} | {status} | {r.get('created','')} | "
                    f"{r.get('last_login','') or '—'} |")
    st.markdown("\n".join(rows))

    st.divider()
    st.markdown("**Add a user**")
    c1, c2 = st.columns([2, 1])
    nn = c1.text_input("Username", key="ua_name")
    nr = c2.selectbox("Role", ROLES, index=2, key="ua_role")
    np1 = c1.text_input("Initial password", type="password", key="ua_p1")
    st.caption(f"Minimum {MIN_PASSWORD_LEN} characters. The user is required to choose their own "
               "password at first sign-in, so you will not know their working password.")
    if st.button("Create user", type="primary"):
        ok, m = create_user(app_dir, nn, np1, nr, must_change=True, created_by=user["name"])
        (st.success if ok else st.error)(m)
        if ok:
            audit(app_dir, user, "user_create", nn.strip(), detail=f"role={nr}")
            st.rerun()

    if not users:
        return

    st.divider()
    st.markdown("**Manage an existing user**")
    pick = st.selectbox("User", ["—"] + sorted(users, key=str.lower), key="um_pick")
    if pick == "—":
        return
    rec = users[pick]
    m1, m2, m3 = st.columns(3)

    new_role = m1.selectbox("Role", ROLES, index=ROLES.index(rec.get("role", "Operator")),
                            key="um_role")
    if m1.button("Apply role", use_container_width=True):
        ok, m = update_user(app_dir, pick, role=new_role)
        (st.success if ok else st.error)(m)
        if ok:
            audit(app_dir, user, "user_role_change", pick, detail=f"role={new_role}")
            st.rerun()

    lbl = "Enable" if rec.get("disabled") else "Disable"
    if m2.button(f"{lbl} account", use_container_width=True):
        ok, m = update_user(app_dir, pick, disabled=not rec.get("disabled"))
        (st.success if ok else st.error)(m)
        if ok:
            audit(app_dir, user, "user_" + lbl.lower(), pick)
            st.rerun()

    if m3.button("Delete account", type="secondary", use_container_width=True):
        ok, m = delete_user(app_dir, pick)
        (st.success if ok else st.error)(m)
        if ok:
            audit(app_dir, user, "user_delete", pick)
            st.rerun()

    rp = st.text_input(f"Reset password for '{pick}'", type="password", key="um_rp")
    if st.button("Reset password"):
        ok, m = set_password(app_dir, pick, rp, must_change=True)
        (st.success if ok else st.error)(m)
        if ok:
            audit(app_dir, user, "user_password_reset", pick)
            st.rerun()


def render_activity_tab(app_dir, user):
    require_role(user, "Admin")
    st.subheader("Activity log")
    events = read_audit(app_dir)
    if not events:
        st.info("No activity recorded yet.")
        return
    st.caption(f"{len(events)} most recent event(s), newest first, from `{AUDIT_FILE}`. "
               "Timestamps come from this machine's clock — on an air-gapped PC there is no "
               "time synchronisation, so verify the system date and time periodically.")

    c1, c2 = st.columns(2)
    who = c1.selectbox("User", ["(all)"] + sorted({e.get("user", "") for e in events}), key="al_who")
    what = c2.selectbox("Action", ["(all)"] + sorted({e.get("action", "") for e in events}),
                        key="al_what")
    sel = [e for e in events
           if (who == "(all)" or e.get("user") == who)
           and (what == "(all)" or e.get("action") == what)]

    rows = ["| when | user | role | action | object | outcome |", "|---|---|---|---|---|---|"]
    for e in sel[:400]:
        rows.append(f"| {e.get('ts','')} | {e.get('user','')} | {e.get('role','')} | "
                    f"{e.get('action','')} | {e.get('object','')} | {e.get('outcome','')} |")
    st.markdown("\n".join(rows))
    if len(sel) > 400:
        st.caption(f"Showing the newest 400 of {len(sel)} matching events — export for the rest.")

    st.download_button("Export activity log (CSV)", audit_csv(sel),
                       file_name="disc5_activity_log.csv", mime="text/csv",
                       use_container_width=True)
