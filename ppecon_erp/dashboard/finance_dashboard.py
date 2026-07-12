# # apps/ppecon_erp/ppecon_erp/dashboard/finance_dashboard.py
# import frappe
# from frappe.utils import flt


# @frappe.whitelist()
# def get_dashboard_data(from_date, to_date, company=None, cost_center=None):
# 	filters = {"from_date": from_date, "to_date": to_date, "company": company, "cost_center": cost_center}

# 	company_cond = "AND company = %(company)s" if company else ""
# 	gle_company_cond = "AND gle.company = %(company)s" if company else ""
# 	gle_cc_cond = "AND gle.cost_center = %(cost_center)s" if cost_center else ""

# 	# ---------- Receivable / Payable ----------
# 	total_receivable = flt(frappe.db.sql(f"""
# 		SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
# 		WHERE docstatus=1 AND outstanding_amount>0 {company_cond}
# 	""", filters)[0][0])

# 	total_payable = flt(frappe.db.sql(f"""
# 		SELECT SUM(outstanding_amount) FROM `tabPurchase Invoice`
# 		WHERE docstatus=1 AND outstanding_amount>0 {company_cond}
# 	""", filters)[0][0])

# 	overdue_receivable = flt(frappe.db.sql(f"""
# 		SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
# 		WHERE docstatus=1 AND outstanding_amount>0 AND due_date < CURDATE() {company_cond}
# 	""", filters)[0][0])

# 	overdue_payable = flt(frappe.db.sql(f"""
# 		SELECT SUM(outstanding_amount) FROM `tabPurchase Invoice`
# 		WHERE docstatus=1 AND outstanding_amount>0 AND due_date < CURDATE() {company_cond}
# 	""", filters)[0][0])

# 	# ---------- Income ----------
# 	income = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.credit - gle.debit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.root_type='Income' AND gle.is_cancelled=0
# 		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	# ---------- Cost of Sales (COGS) ----------
# 	# Requires accounts to have Account Type = "Cost of Goods Sold" set correctly
# 	cost_of_sales = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.account_type='Cost of Goods Sold' AND gle.is_cancelled=0
# 		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	# ---------- Total Expense (everything under root_type Expense, includes COGS) ----------
# 	total_expense = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.root_type='Expense' AND gle.is_cancelled=0
# 		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	# ---------- Operating Expenses = Total Expense - Cost of Sales ----------
# 	operating_expense = total_expense - cost_of_sales

# 	# ---------- Derived P&L figures ----------
# 	gross_profit = income - cost_of_sales
# 	net_profit = income - total_expense

# 	def pct(part, whole):
# 		return round((part / whole) * 100, 1) if whole else 0

# 	pl_breakdown = {
# 		"income": income,
# 		"income_pct": 100.0 if income else 0,
# 		"cost_of_sales": cost_of_sales,
# 		"cost_of_sales_pct": pct(cost_of_sales, income),
# 		"gross_profit": gross_profit,
# 		"gross_profit_pct": pct(gross_profit, income),
# 		"operating_expense": operating_expense,
# 		"operating_expense_pct": pct(operating_expense, income),
# 		"net_profit": net_profit,
# 		"net_profit_pct": pct(net_profit, income),
# 	}

# 	# ---------- Closing balances ----------
# 	cash_balance = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.account_type='Cash' AND gle.is_cancelled=0
# 		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	bank_balance = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.account_type='Bank' AND gle.is_cancelled=0
# 		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	total_assets = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.root_type='Asset' AND gle.is_cancelled=0
# 		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	total_liabilities = flt(frappe.db.sql(f"""
# 		SELECT SUM(gle.credit - gle.debit) FROM `tabGL Entry` gle
# 		JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE acc.root_type='Liability' AND gle.is_cancelled=0
# 		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond}
# 	""", filters)[0][0])

# 	# ---------- Top customers / suppliers ----------
# 	pe_company_cond = "AND company = %(company)s" if company else ""
# 	pe_cc_cond = "AND cost_center = %(cost_center)s" if cost_center else ""

# 	# All customers (no limit) who received payment in the period, sorted highest first
# 	top_customers = frappe.db.sql(f"""
# 		SELECT party, SUM(paid_amount) as total
# 		FROM `tabPayment Entry`
# 		WHERE payment_type='Receive' AND docstatus=1 AND party_type='Customer'
# 		AND posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{pe_company_cond} {pe_cc_cond}
# 		GROUP BY party ORDER BY total DESC
# 	""", filters, as_dict=True)

# 	# All suppliers (no limit) who were paid in the period, sorted highest first
# 	top_suppliers = frappe.db.sql(f"""
# 		SELECT party, SUM(paid_amount) as total
# 		FROM `tabPayment Entry`
# 		WHERE payment_type='Pay' AND docstatus=1 AND party_type='Supplier'
# 		AND posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{pe_company_cond} {pe_cc_cond}
# 		GROUP BY party ORDER BY total DESC
# 	""", filters, as_dict=True)

# 	total_received = sum([flt(r.total) for r in top_customers])
# 	total_paid = sum([flt(r.total) for r in top_suppliers])

# 	# ---------- Monthly trend ----------
# 	monthly_trend = frappe.db.sql(f"""
# 		SELECT DATE_FORMAT(gle.posting_date, '%%b %%Y') as month,
# 		SUM(CASE WHEN acc.root_type='Income' THEN gle.credit-gle.debit ELSE 0 END) as income,
# 		SUM(CASE WHEN acc.root_type='Expense' THEN gle.debit-gle.credit ELSE 0 END) as expense
# 		FROM `tabGL Entry` gle JOIN `tabAccount` acc ON gle.account = acc.name
# 		WHERE gle.is_cancelled=0 AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
# 		{gle_company_cond} {gle_cc_cond}
# 		GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
# 		ORDER BY MIN(gle.posting_date)
# 	""", filters, as_dict=True)

# 	for row in monthly_trend:
# 		row["net_profit"] = flt(row.income) - flt(row.expense)

# 	return {
# 		"receivable": total_receivable,
# 		"payable": total_payable,
# 		"overdue_receivable": overdue_receivable,
# 		"overdue_payable": overdue_payable,
# 		"income": income,
# 		"expense": total_expense,
# 		"net_profit": net_profit,
# 		"profit_margin": pct(net_profit, income),
# 		"cash_balance": cash_balance,
# 		"bank_balance": bank_balance,
# 		"total_assets": total_assets,
# 		"total_liabilities": total_liabilities,
# 		"total_received": total_received,
# 		"total_paid": total_paid,
# 		"top_customers": top_customers,
# 		"top_suppliers": top_suppliers,
# 		"monthly_trend": monthly_trend,
# 		"pl_breakdown": pl_breakdown,
# 	}



# apps/ppecon_erp/ppecon_erp/dashboard/finance_dashboard.py
import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_dashboard_data(from_date, to_date, company=None, cost_center=None, project=None):
	filters = {
		"from_date": from_date, "to_date": to_date,
		"company": company, "cost_center": cost_center, "project": project,
	}

	company_cond = "AND company = %(company)s" if company else ""
	gle_company_cond = "AND gle.company = %(company)s" if company else ""
	gle_cc_cond = "AND gle.cost_center = %(cost_center)s" if cost_center else ""
	gle_project_cond = "AND gle.project = %(project)s" if project else ""
	si_project_cond = "AND project = %(project)s" if project else ""

	# ---------- Receivable / Payable ----------
	total_receivable = flt(frappe.db.sql(f"""
		SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount>0 {company_cond} {si_project_cond}
	""", filters)[0][0])

	total_payable = flt(frappe.db.sql(f"""
		SELECT SUM(outstanding_amount) FROM `tabPurchase Invoice`
		WHERE docstatus=1 AND outstanding_amount>0 {company_cond} {si_project_cond}
	""", filters)[0][0])

	overdue_receivable = flt(frappe.db.sql(f"""
		SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount>0 AND due_date < CURDATE() {company_cond} {si_project_cond}
	""", filters)[0][0])

	overdue_payable = flt(frappe.db.sql(f"""
		SELECT SUM(outstanding_amount) FROM `tabPurchase Invoice`
		WHERE docstatus=1 AND outstanding_amount>0 AND due_date < CURDATE() {company_cond} {si_project_cond}
	""", filters)[0][0])

	# ---------- Income ----------
	income = flt(frappe.db.sql(f"""
		SELECT SUM(gle.credit - gle.debit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.root_type='Income' AND gle.is_cancelled=0
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	# ---------- Cost of Sales (COGS) ----------
	cost_of_sales = flt(frappe.db.sql(f"""
		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.account_type='Cost of Goods Sold' AND gle.is_cancelled=0
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	# ---------- Total Expense ----------
	total_expense = flt(frappe.db.sql(f"""
		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.root_type='Expense' AND gle.is_cancelled=0
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	operating_expense = total_expense - cost_of_sales
	gross_profit = income - cost_of_sales
	net_profit = income - total_expense

	def pct(part, whole):
		return round((part / whole) * 100, 1) if whole else 0

	pl_breakdown = {
		"income": income,
		"income_pct": 100.0 if income else 0,
		"cost_of_sales": cost_of_sales,
		"cost_of_sales_pct": pct(cost_of_sales, income),
		"gross_profit": gross_profit,
		"gross_profit_pct": pct(gross_profit, income),
		"operating_expense": operating_expense,
		"operating_expense_pct": pct(operating_expense, income),
		"net_profit": net_profit,
		"net_profit_pct": pct(net_profit, income),
	}

	# ---------- Closing balances (project filter applies here too) ----------
	cash_balance = flt(frappe.db.sql(f"""
		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.account_type='Cash' AND gle.is_cancelled=0
		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	bank_balance = flt(frappe.db.sql(f"""
		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.account_type='Bank' AND gle.is_cancelled=0
		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	total_assets = flt(frappe.db.sql(f"""
		SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.root_type='Asset' AND gle.is_cancelled=0
		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	total_liabilities = flt(frappe.db.sql(f"""
		SELECT SUM(gle.credit - gle.debit) FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE acc.root_type='Liability' AND gle.is_cancelled=0
		AND gle.posting_date <= %(to_date)s {gle_company_cond} {gle_cc_cond} {gle_project_cond}
	""", filters)[0][0])

	# ---------- Top customers / suppliers ----------
	pe_company_cond = "AND pe.company = %(company)s" if company else ""

	if project:
		# When a project is selected, attribute payments through invoice references
		top_customers = frappe.db.sql(f"""
			SELECT pe.party, SUM(per.allocated_amount) as total
			FROM `tabPayment Entry Reference` per
			JOIN `tabPayment Entry` pe ON pe.name = per.parent
			JOIN `tabSales Invoice` si ON si.name = per.reference_name
			WHERE pe.docstatus=1 AND pe.payment_type='Receive'
			AND per.reference_doctype='Sales Invoice'
			AND si.project = %(project)s
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{pe_company_cond}
			GROUP BY pe.party ORDER BY total DESC
		""", filters, as_dict=True)

		top_suppliers = frappe.db.sql(f"""
			SELECT pe.party, SUM(per.allocated_amount) as total
			FROM `tabPayment Entry Reference` per
			JOIN `tabPayment Entry` pe ON pe.name = per.parent
			JOIN `tabPurchase Invoice` pi ON pi.name = per.reference_name
			WHERE pe.docstatus=1 AND pe.payment_type='Pay'
			AND per.reference_doctype='Purchase Invoice'
			AND pi.project = %(project)s
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{pe_company_cond}
			GROUP BY pe.party ORDER BY total DESC
		""", filters, as_dict=True)
	else:
		pe_company_cond2 = "AND company = %(company)s" if company else ""
		pe_cc_cond = "AND cost_center = %(cost_center)s" if cost_center else ""
		top_customers = frappe.db.sql(f"""
			SELECT party, SUM(paid_amount) as total
			FROM `tabPayment Entry`
			WHERE payment_type='Receive' AND docstatus=1 AND party_type='Customer'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			{pe_company_cond2} {pe_cc_cond}
			GROUP BY party ORDER BY total DESC
		""", filters, as_dict=True)

		top_suppliers = frappe.db.sql(f"""
			SELECT party, SUM(paid_amount) as total
			FROM `tabPayment Entry`
			WHERE payment_type='Pay' AND docstatus=1 AND party_type='Supplier'
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			{pe_company_cond2} {pe_cc_cond}
			GROUP BY party ORDER BY total DESC
		""", filters, as_dict=True)

	total_received = sum([flt(r.total) for r in top_customers])
	total_paid = sum([flt(r.total) for r in top_suppliers])

	# ---------- Monthly trend ----------
	monthly_trend = frappe.db.sql(f"""
		SELECT DATE_FORMAT(gle.posting_date, '%%b %%Y') as month,
		SUM(CASE WHEN acc.root_type='Income' THEN gle.credit-gle.debit ELSE 0 END) as income,
		SUM(CASE WHEN acc.root_type='Expense' THEN gle.debit-gle.credit ELSE 0 END) as expense
		FROM `tabGL Entry` gle JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE gle.is_cancelled=0 AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{gle_company_cond} {gle_cc_cond} {gle_project_cond}
		GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
		ORDER BY MIN(gle.posting_date)
	""", filters, as_dict=True)

	for row in monthly_trend:
		row["net_profit"] = flt(row.income) - flt(row.expense)

	# ---------- Project-wise breakdown (always returned) ----------
	project_breakdown = frappe.db.sql(f"""
		SELECT COALESCE(NULLIF(gle.project, ''), 'No Project') as project,
		SUM(CASE WHEN acc.root_type='Income' THEN gle.credit-gle.debit ELSE 0 END) as income,
		SUM(CASE WHEN acc.root_type='Expense' THEN gle.debit-gle.credit ELSE 0 END) as expense
		FROM `tabGL Entry` gle JOIN `tabAccount` acc ON gle.account = acc.name
		WHERE gle.is_cancelled=0
		AND acc.root_type IN ('Income','Expense')
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		{gle_company_cond} {gle_cc_cond}
		GROUP BY COALESCE(NULLIF(gle.project, ''), 'No Project')
		ORDER BY expense DESC
	""", filters, as_dict=True)

	for row in project_breakdown:
		row["profit"] = flt(row.income) - flt(row.expense)

	# ---------- Project summary (only when a project is selected) ----------
	project_summary = None
	if project:
		proj = frappe.db.get_value("Project", project,
			["project_name", "status", "percent_complete",
			 "total_sales_amount", "total_billed_amount", "estimated_costing"],
			as_dict=1) or frappe._dict()

		# Total billed to client for this project (all time, submitted invoices)
		billed = flt(frappe.db.sql(f"""
			SELECT SUM(base_grand_total) FROM `tabSales Invoice`
			WHERE docstatus=1 AND project = %(project)s {company_cond}
		""", filters)[0][0])

		# Total received from client against this project's invoices (all time)
		received = flt(frappe.db.sql("""
			SELECT SUM(per.allocated_amount)
			FROM `tabPayment Entry Reference` per
			JOIN `tabPayment Entry` pe ON pe.name = per.parent
			JOIN `tabSales Invoice` si ON si.name = per.reference_name
			WHERE pe.docstatus=1 AND pe.payment_type='Receive'
			AND per.reference_doctype='Sales Invoice'
			AND si.project = %(project)s
		""", filters)[0][0])

		outstanding = flt(frappe.db.sql(f"""
			SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
			WHERE docstatus=1 AND outstanding_amount>0 AND project = %(project)s {company_cond}
		""", filters)[0][0])

		project_summary = {
			"project": project,
			"project_name": proj.get("project_name") or project,
			"status": proj.get("status"),
			"percent_complete": flt(proj.get("percent_complete")),
			"contract_value": flt(proj.get("total_sales_amount")),  # from linked Sales Orders
			"estimated_costing": flt(proj.get("estimated_costing")),
			"billed": billed,
			"received": received,
			"outstanding": outstanding,
			"income": income,            # period income for this project (GL)
			"expense": total_expense,    # period expense for this project (GL)
			"profit": net_profit,
		}

	return {
		"receivable": total_receivable,
		"payable": total_payable,
		"overdue_receivable": overdue_receivable,
		"overdue_payable": overdue_payable,
		"income": income,
		"expense": total_expense,
		"net_profit": net_profit,
		"profit_margin": pct(net_profit, income),
		"cash_balance": cash_balance,
		"bank_balance": bank_balance,
		"total_assets": total_assets,
		"total_liabilities": total_liabilities,
		"total_received": total_received,
		"total_paid": total_paid,
		"top_customers": top_customers,
		"top_suppliers": top_suppliers,
		"monthly_trend": monthly_trend,
		"pl_breakdown": pl_breakdown,
		"project_breakdown": project_breakdown,
		"project_summary": project_summary,
	}