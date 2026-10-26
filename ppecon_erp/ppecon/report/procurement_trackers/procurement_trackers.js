// Copyright (c) 2026, altamash and contributors
// For license information, please see license.txt

frappe.query_reports["Procurement Trackers"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "status",
			label: __("MR Status"),
			fieldtype: "Select",
			options: [
				"",
				"Pending",
				"Partially Ordered",
				"Ordered",
				"Partially Received",
				"Received",
				"Issued",
				"Transferred",
				"Stopped",
			].join("\n"),
		},
		{
			fieldname: "material_request",
			label: __("Material Request"),
			fieldtype: "Link",
			options: "Material Request",
		},
	],
};
