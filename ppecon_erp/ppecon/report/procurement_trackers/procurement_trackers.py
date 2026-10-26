# Copyright (c) 2026, altamash and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
	columns, data = [], []
	return columns, data



import frappe
from frappe import _
from frappe.utils import flt, getdate

CHUNK = 2000  # max IN (...) size per query


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()

    # never scan the whole company history: need at least one narrowing filter
    if not (filters.project or filters.material_request or filters.from_date or filters.to_date):
        return columns, [], _("Select a Project, a Material Request or a Date range to load data.")

    if filters.from_date and filters.to_date and getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date."))

    return columns, get_data(filters)


# ---------------------------------------------------------------- columns
def get_columns():
    return [
        {"label": _("Material Request"), "fieldname": "material_request", "fieldtype": "Link", "options": "Material Request", "width": 150},
        {"label": _("Material Title"), "fieldname": "material_title", "fieldtype": "Data", "width": 180},
        {"label": _("MR Status"), "fieldname": "mr_status", "fieldtype": "Data", "width": 110},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Data", "width": 160},
        {"label": _("MR Date"), "fieldname": "mr_date", "fieldtype": "Date", "width": 95},

        {"label": _("Supplier Quotation"), "fieldname": "supplier_quotation", "fieldtype": "Link", "options": "Supplier Quotation", "width": 150},
        {"label": _("SQ Date"), "fieldname": "sq_date", "fieldtype": "Date", "width": 95},
        {"label": _("SQ Status"), "fieldname": "sq_status", "fieldtype": "Data", "width": 110},
        {"label": _("SQ Total"), "fieldname": "sq_total", "fieldtype": "Currency", "width": 110},

        {"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
        {"label": _("PO Date"), "fieldname": "po_date", "fieldtype": "Date", "width": 95},
        {"label": _("PO Supplier"), "fieldname": "po_supplier", "fieldtype": "Data", "width": 160},
        {"label": _("PO Total"), "fieldname": "po_total", "fieldtype": "Currency", "width": 110},

        {"label": _("Payment Request"), "fieldname": "payment_request", "fieldtype": "Link", "options": "Payment Request", "width": 150},
        {"label": _("PR Date"), "fieldname": "pr_date", "fieldtype": "Date", "width": 95},
        {"label": _("PR Party"), "fieldname": "pr_party", "fieldtype": "Data", "width": 150},
        {"label": _("PR Total"), "fieldname": "pr_total", "fieldtype": "Currency", "width": 110},

        {"label": _("Payment Entries"), "fieldname": "payment_entries", "fieldtype": "Data", "width": 200},
        {"label": _("PE Dates"), "fieldname": "pe_dates", "fieldtype": "Data", "width": 140},
        {"label": _("Cheque"), "fieldname": "cheque", "fieldtype": "Data", "width": 130},
        {"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 120},
    ]


# ---------------------------------------------------------------- helpers
def _chunks(seq, size=CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _query_in(sql, names, extra=None):
    """Run `sql` (containing %(names)s) in chunks so huge IN lists never choke MariaDB."""
    out = []
    for part in _chunks(names):
        params = {"names": tuple(part)}
        params.update(extra or {})
        out.extend(frappe.db.sql(sql, params, as_dict=True))
    return out


# ---------------------------------------------------------------- data
def get_data(filters):
    mrs = get_material_requests(filters)
    if not mrs:
        return []

    mr_names = [m.name for m in mrs]
    item_projects = get_item_projects(mr_names)
    sq_by_mr = get_supplier_quotations(mr_names)
    po_by_mr = get_purchase_orders(mr_names)

    po_names = {p.name for rows in po_by_mr.values() for p in rows}
    pr_by_po = get_payment_requests(po_names)
    pe_by_po = get_payment_entries(po_names)

    data = []
    for mr in mrs:
        project = item_projects.get(mr.name) or mr.custom_project_name or ""
        sqs = sq_by_mr.get(mr.name) or [None]
        pos = po_by_mr.get(mr.name) or [None]

        # same grain as the old report: one row per MR x SQ x PO x Payment Request
        for sq in sqs:
            for po in pos:
                prs = (pr_by_po.get(po.name) if po else None) or [None]
                pe = pe_by_po.get(po.name) if po else None
                for pr in prs:
                    data.append({
                        "material_request": mr.name,
                        "material_title": mr.custom_material_title,
                        "mr_status": mr.status,
                        "project": project,
                        "mr_date": mr.transaction_date,

                        "supplier_quotation": sq.name if sq else None,
                        "sq_date": sq.transaction_date if sq else None,
                        "sq_status": sq.workflow_state if sq else None,
                        "sq_total": sq.grand_total if sq else None,

                        "purchase_order": po.name if po else None,
                        "po_date": po.transaction_date if po else None,
                        "po_supplier": po.supplier if po else None,
                        "po_total": po.grand_total if po else None,

                        "payment_request": pr.name if pr else None,
                        "pr_date": pr.transaction_date if pr else None,
                        "pr_party": pr.party if pr else None,
                        "pr_total": pr.grand_total if pr else None,

                        "payment_entries": pe["entries"] if pe else "None",
                        "pe_dates": pe["dates"] if pe else "None",
                        "cheque": pe["cheque"] if pe else "None",
                        "total_amount": pe["total"] if pe else 0,
                    })
    return data


def get_material_requests(filters):
    conditions = ["mr.docstatus = 1"]
    params = {}

    if filters.material_request:
        conditions.append("mr.name = %(material_request)s")
        params["material_request"] = filters.material_request
    if filters.status:
        conditions.append("mr.status = %(status)s")
        params["status"] = filters.status
    if filters.from_date:
        conditions.append("mr.transaction_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("mr.transaction_date <= %(to_date)s")
        params["to_date"] = filters.to_date
    if filters.project:
        # project can sit on the MR header or on its items
        conditions.append(
            "(mr.custom_project_name = %(project)s OR EXISTS ("
            "SELECT 1 FROM `tabMaterial Request Item` mri "
            "WHERE mri.parent = mr.name AND mri.project = %(project)s))"
        )
        params["project"] = filters.project

    return frappe.db.sql(
        """
        SELECT mr.name, mr.custom_material_title, mr.status,
               mr.custom_project_name, mr.transaction_date
        FROM `tabMaterial Request` mr
        WHERE {where}
        ORDER BY mr.transaction_date DESC, mr.name DESC
        """.format(where=" AND ".join(conditions)),
        params, as_dict=True,
    )


def get_item_projects(mr_names):
    rows = _query_in(
        """
        SELECT parent, GROUP_CONCAT(DISTINCT project ORDER BY project SEPARATOR ', ') AS projects
        FROM `tabMaterial Request Item`
        WHERE parent IN %(names)s AND IFNULL(project, '') != ''
        GROUP BY parent
        """,
        mr_names,
    )
    return {r.parent: r.projects for r in rows}


def get_supplier_quotations(mr_names):
    rows = _query_in(
        """
        SELECT DISTINCT sqi.material_request AS mr, sq.name, sq.transaction_date,
               sq.workflow_state, sq.grand_total
        FROM `tabSupplier Quotation Item` sqi
        JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
        WHERE sqi.material_request IN %(names)s AND sq.docstatus = 1
        ORDER BY sq.transaction_date, sq.name
        """,
        mr_names,
    )
    out = {}
    for r in rows:
        out.setdefault(r.mr, []).append(r)
    return out


def get_purchase_orders(mr_names):
    rows = _query_in(
        """
        SELECT DISTINCT poi.material_request AS mr, po.name, po.transaction_date,
               po.supplier, po.grand_total
        FROM `tabPurchase Order Item` poi
        JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.material_request IN %(names)s AND po.docstatus = 1
        ORDER BY po.transaction_date, po.name
        """,
        mr_names,
    )
    out = {}
    for r in rows:
        out.setdefault(r.mr, []).append(r)
    return out


def get_payment_requests(po_names):
    if not po_names:
        return {}
    rows = _query_in(
        """
        SELECT pr.reference_name AS po, pr.name, pr.transaction_date, pr.party, pr.grand_total
        FROM `tabPayment Request` pr
        WHERE pr.reference_doctype = 'Purchase Order'
          AND pr.reference_name IN %(names)s AND pr.docstatus < 2
        ORDER BY pr.transaction_date, pr.name
        """,
        po_names,
    )
    out = {}
    for r in rows:
        out.setdefault(r.po, []).append(r)
    return out


def get_payment_entries(po_names):
    """All Payment Entries per PO in ONE query (no per-row subqueries)."""
    if not po_names:
        return {}
    rows = _query_in(
        """
        SELECT per.reference_name AS po, pe.name, pe.posting_date, pe.reference_no,
               per.allocated_amount
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Purchase Order'
          AND per.reference_name IN %(names)s AND pe.docstatus = 1
        ORDER BY pe.posting_date, pe.name
        """,
        po_names,
    )

    agg = {}
    for r in rows:
        a = agg.setdefault(r.po, {"entries": [], "dates": [], "cheque": [], "total": 0.0})
        if r.name not in a["entries"]:
            a["entries"].append(r.name)
        d = str(r.posting_date)
        if d not in a["dates"]:
            a["dates"].append(d)
        if r.reference_no and r.reference_no not in a["cheque"]:
            a["cheque"].append(r.reference_no)
        a["total"] += flt(r.allocated_amount)

    return {
        po: {
            "entries": ", ".join(a["entries"]),
            "dates": ", ".join(a["dates"]),
            "cheque": ", ".join(a["cheque"]) or "None",
            "total": a["total"],
        }
        for po, a in agg.items()
    }