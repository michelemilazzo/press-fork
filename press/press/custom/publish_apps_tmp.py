import json
import re
from html.parser import HTMLParser

import frappe
from press.press.doctype.app.app import new_app as new_app_doc

TEAM_PREFERRED = "6b81qcp42g-BcwMMqVR0p"
DEFAULT_VERSION = "Version 16"


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())


def _strip_html(value):
    parser = _HTMLStripper()
    parser.feed(value or "")
    return "\n".join(parser.parts)


def _nice_title(name):
    if name == "press-fork":
        return "Press Fork"
    if name == "mmosa-app":
        return "MMOSA App"
    parts = re.split(r"[-_]+", name)
    title = []
    for part in parts:
        lowered = part.lower()
        if lowered == "mmos":
            title.append("MMOS")
        elif lowered in {"erpnext", "hrms", "lms", "crm", "tse", "otp", "pdf", "vat", "csf", "ke", "eu"}:
            title.append(part.upper())
        elif lowered == "app":
            title.append("App")
        else:
            title.append(part.capitalize())
    return " ".join(title)


def _infer_category(name):
    lowered = name.lower()
    if any(token in lowered for token in ["hetzner", "press", "agent", "telephony"]):
        return "Infrastructure"
    if any(token in lowered for token in ["erpnext", "payments", "pos", "crm", "lending", "gate_entry", "warehouse"]):
        return "ERP & Commerce"
    if any(token in lowered for token in ["compliance", "einvoice", "edocument", "vat", "tse", "swiss_accounting"]):
        return "Compliance & Finance"
    if any(token in lowered for token in ["whatsapp", "mail", "email_delivery", "helpdesk"]):
        return "Integrations"
    if any(token in lowered for token in ["wiki", "blog", "builder", "forms", "portal_theme", "writer", "webapp", "lms", "planner", "insights"]):
        return "Productivity & Content"
    return "Business Utilities"


def _build_summary(name, title, long_description):
    text = _strip_html(long_description)
    lines = [re.sub(r"\s+", " ", line).strip(" -*#`:") for line in text.splitlines()]
    lines = [
        line
        for line in lines
        if line
        and len(line) > 20
        and line[0].isalnum()
        and not line.lower().startswith(("license", "copyright"))
    ]
    for line in lines:
        if title.lower() in line.lower() and len(line) <= 160:
            return line[:160]
    for line in lines:
        if len(line) <= 160:
            return line[:160]
    return f"{title} for {_infer_category(name).lower()} workflows on Frappe and ERPNext."


def _ensure_categories():
    categories = {
        "Infrastructure": "Hosting, servers, deployment and operations.",
        "ERP & Commerce": "ERP, sales, finance and operational extensions.",
        "Compliance & Finance": "Tax, compliance, invoicing and accounting features.",
        "Integrations": "Messaging, email and external service integrations.",
        "Productivity & Content": "Knowledge, collaboration, forms and content tools.",
        "Business Utilities": "General business extensions and utilities.",
    }
    for name, description in categories.items():
        if not frappe.db.exists("Marketplace App Category", name):
            frappe.get_doc(
                {
                    "doctype": "Marketplace App Category",
                    "name": name,
                    "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
                    "description": description,
                }
            ).insert(ignore_permissions=True)


def _update_marketplace_metadata(mp, repo_url):
    title = _nice_title(mp.name)
    category = _infer_category(mp.name)
    mp.title = title
    if not mp.description or mp.description.strip() == "Please add a short description about your app here...":
        mp.description = _build_summary(mp.name, title, mp.long_description)
    if repo_url:
        if not mp.website:
            mp.website = repo_url
        if not mp.documentation:
            mp.documentation = repo_url
        if not mp.support:
            mp.support = f"{repo_url}/issues"
    mp.set("categories", [{"category": category}])


def run():
    with open('/tmp/repos.json') as f:
        repos = json.load(f)

    teams = frappe.get_all('Team', pluck='name')
    if TEAM_PREFERRED in teams:
        team = TEAM_PREFERRED
    elif teams:
        team = teams[0]
    else:
        team = None

    _ensure_categories()

    created = []
    updated = []
    errors = []

    for repo in repos:
        name = repo['name']
        branches = repo['branches']
        if not branches:
            continue
        title = _nice_title(name)
        try:
            if not frappe.db.exists('App', name):
                app = new_app_doc(name, title)
                app.team = team
                app.public = 1
                app.enabled = 1
                app.save()
                created.append(name)
            app = frappe.get_doc('App', name)

            for branch in branches:
                repo_url = f"https://github.com/michelemilazzo/{name}.git"
                source = app.add_source(
                    repository_url=repo_url,
                    branch=branch,
                    frappe_version=DEFAULT_VERSION,
                    team=team,
                    public=True,
                    repository_owner='michelemilazzo',
                )
                source.enabled = 1
                source.save()
                source.create_release(force=True)

                rel_name = frappe.db.get_value('App Release', {"source": source.name}, order_by="creation desc")
                if rel_name:
                    rel = frappe.get_doc('App Release', rel_name)
                    rel.status = 'Approved'
                    rel.public = 1
                    rel.save()

            if not frappe.db.exists('Marketplace App', name):
                mp = frappe.get_doc({
                    'doctype': 'Marketplace App',
                    'app': name,
                    'title': title,
                    'team': team,
                    'status': 'Published',
                    'published': 1,
                    'frappe_approved': 1,
                }).insert()
            else:
                mp = frappe.get_doc('Marketplace App', name)

            existing = {(s.version, s.source) for s in mp.sources}
            sources = frappe.get_all('App Source', {'app': name, 'team': team}, pluck='name')
            for src in sources:
                key = (DEFAULT_VERSION, src)
                if key not in existing:
                    mp.append('sources', {'version': DEFAULT_VERSION, 'source': src})
            mp.status = 'Published'
            mp.published = 1
            mp.frappe_approved = 1
            _update_marketplace_metadata(mp, repo_url)
            mp.save()
            updated.append(name)
        except Exception as e:
            errors.append((name, str(e)))

    frappe.db.commit()
    print('created', len(created))
    print('updated', len(updated))
    print('errors', len(errors))
    for n, e in errors:
        print(n, e)
