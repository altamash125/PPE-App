// Copyright (c) 2026, altamash and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Total row
		if (data.employee_name === "── TOTAL ──") {
			value = `<b style="color:#1a5276;font-size:13px">${value}</b>`;
		}

		// Friday = blue
		if (data.day_type === "Friday") {
			value = `<span style="color:#1a6dab;font-weight:600">${value}</span>`;
		}

		// Holiday = orange
		if (data.day_type === "Holiday") {
			value = `<span style="color:#ca6f1e;font-weight:600">${value}</span>`;
		}

		// OT amount = green bold
		if (column.fieldname === "overtime_amount" && data.overtime_amount > 0) {
			value = `<b style="color:#1e8449">${value}</b>`;
		}

		// High OT hours = highlight
		if (column.fieldname === "overtime_hours" && data.overtime_hours > 50) {
			value = `<span style="color:#c0392b;font-weight:600">${value}</span>`;
		}

		return value;
	},
};
