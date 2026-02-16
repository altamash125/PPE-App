# # material_request_tracking/material_request_tracking/api/material_request.py

# import frappe
# from frappe import _
# import json
# from datetime import datetime, date

# @frappe.whitelist(allow_guest=False)
# def get_material_request_tracking(filters=None, sort_by=None):
#     """
#     API to fetch material request tracking data
#     """
    
#     # Parse filters if provided as string
#     if filters and isinstance(filters, str):
#         filters = json.loads(filters)
    
#     # Build the SQL query
#     query = """
#         SELECT
#             mr.name AS material_request,
#             DATE(mr.transaction_date) AS mr_date,
#             COALESCE(mri.project, mr.custom_project_name) AS project,
#             mr.status AS mr_status,
#             sq.name AS supplier_quotation,
#             DATE(sq.transaction_date) AS sq_date,
#             sq.workflow_state AS sq_status,
#             sq.grand_total AS sq_total,
#             po.name AS purchase_order,
#             DATE(po.transaction_date) AS po_date,
#             po.supplier AS po_supplier,
#             po.grand_total AS po_total,
#             po.status AS po_status,
#             COALESCE(
#                 (SELECT MIN(pe2.posting_date)
#                  FROM `tabPayment Entry Reference` per2
#                  JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
#                  WHERE per2.reference_name = po.name AND pe2.docstatus = 1), 
#                 NULL
#             ) AS first_payment_date,
#             COALESCE(
#                 (SELECT GROUP_CONCAT(DISTINCT pe2.name SEPARATOR ', ')
#                  FROM `tabPayment Entry Reference` per2
#                  JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
#                  WHERE per2.reference_name = po.name AND pe2.docstatus = 1), 
#                 NULL
#             ) AS payment_entries,
#             COALESCE(
#                 (SELECT SUM(pe2.paid_amount)
#                  FROM `tabPayment Entry Reference` per2
#                  JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
#                  WHERE per2.reference_name = po.name AND pe2.docstatus = 1), 
#                 0
#             ) AS total_paid
#         FROM `tabMaterial Request` mr
#         LEFT JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
#         LEFT JOIN `tabSupplier Quotation Item` sqi ON sqi.material_request = mr.name
#         LEFT JOIN `tabSupplier Quotation` sq ON sqi.parent = sq.name AND sq.docstatus = 1
#         LEFT JOIN `tabPurchase Order Item` poi ON poi.material_request = mr.name
#         LEFT JOIN `tabPurchase Order` po ON poi.parent = po.name AND po.docstatus = 1
#         WHERE mr.docstatus = 1
#     """

#     # Add filters
#     conditions = []
#     values = {}

#     if filters:
#         if filters.get('mr_status') and len(filters['mr_status']) > 0:
#             placeholders = ', '.join(['%s'] * len(filters['mr_status']))
#             conditions.append(f"mr.status IN ({placeholders})")
#             values.update({f'status_{i}': status for i, status in enumerate(filters['mr_status'])})
        
#         if filters.get('project'):
#             conditions.append("(mri.project LIKE %(project)s OR mr.custom_project_name LIKE %(project)s)")
#             values['project'] = f"%{filters['project']}%"
        
#         if filters.get('supplier'):
#             conditions.append("po.supplier LIKE %(supplier)s")
#             values['supplier'] = f"%{filters['supplier']}%"
        
#         if filters.get('from_date'):
#             conditions.append("DATE(mr.transaction_date) >= %(from_date)s")
#             values['from_date'] = filters['from_date']
        
#         if filters.get('to_date'):
#             conditions.append("DATE(mr.transaction_date) <= %(to_date)s")
#             values['to_date'] = filters['to_date']

#     if conditions:
#         query += " AND " + " AND ".join(conditions)

#     query += " GROUP BY mr.name, sq.name, po.name"

#     try:
#         raw_data = frappe.db.sql(query, values, as_dict=True)
        
#         # Process data to add delay calculations
#         processed_data = []
#         for row in raw_data:
#             processed_row = dict(row)
            
#             # Calculate delays
#             processed_row['mr_sq_delay_days'] = calculate_delay(
#                 row.get('mr_date'), 
#                 row.get('sq_date')
#             )
#             processed_row['sq_po_delay_days'] = calculate_delay(
#                 row.get('sq_date'), 
#                 row.get('po_date')
#             )
#             processed_row['po_payment_delay_days'] = calculate_delay(
#                 row.get('po_date'), 
#                 row.get('first_payment_date')
#             )
            
#             processed_data.append(processed_row)
        
#         # Apply sorting
#         if sort_by:
#             processed_data = sort_data(processed_data, sort_by)
        
#         return {
#             'status': 'success',
#             'data': processed_data,
#             'total_count': len(processed_data)
#         }
        
#     except Exception as e:
#         frappe.log_error(f"Error in material request tracking: {str(e)}", "Material Request Tracking")
#         return {
#             'status': 'error',
#             'message': str(e)
#         }

# def calculate_delay(start_date, end_date):
#     """Calculate delay in days between two dates"""
#     if not start_date or not end_date:
#         return None
    
#     if isinstance(start_date, str):
#         start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
#     if isinstance(end_date, str):
#         end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
#     delta = end_date - start_date
#     return delta.days

# def sort_data(data, sort_by):
#     """Sort data based on specified option"""
#     if sort_by == 'mr_date_first':
#         return sorted(data, key=lambda x: (x.get('mr_date') or date.min), reverse=True)
#     elif sort_by == 'sq_date_first':
#         return sorted(data, key=lambda x: (x.get('sq_date') or date.min), reverse=True)
#     elif sort_by == 'id_first':
#         return sorted(data, key=lambda x: x.get('material_request') or '')
#     elif sort_by == 'process':
#         def process_score(row):
#             if row.get('payment_entries'):
#                 return 1
#             elif row.get('purchase_order'):
#                 return 2
#             elif row.get('supplier_quotation'):
#                 return 3
#             else:
#                 return 4
#         return sorted(data, key=lambda x: (process_score(x), x.get('mr_date') or date.min))
#     return data

# @frappe.whitelist(allow_guest=False)
# def get_filter_options():
#     """Get filter options for the dashboard"""
#     try:
#         mr_statuses = frappe.db.sql_list("""
#             SELECT DISTINCT status 
#             FROM `tabMaterial Request` 
#             WHERE docstatus = 1 
#             ORDER BY status
#         """)
        
#         return {
#             'status': 'success',
#             'filters': {
#                 'mr_statuses': mr_statuses
#             }
#         }
#     except Exception as e:
#         return {
#             'status': 'error',
#             'message': str(e)
#         }


# material_request_tracking/material_request_tracking/api/material_request.py

import frappe
from frappe import _
import json
from datetime import datetime, date

@frappe.whitelist()
def get_material_request_tracking(filters=None, sort_by=None):
    """
    API to fetch material request tracking data with delay calculations
    sort_by options: mr_date_first, sq_date_first, id_first, process
    """
    
    # Parse filters if provided as string
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    
    # Base SQL query
    query = """
        SELECT
            mr.name AS `material_request`,
            DATE(mr.transaction_date) AS `mr_date`,
            COALESCE(mri.project, mr.custom_project_name) AS `project`,
            mr.status AS `mr_status`,

            -- Supplier Quotation
            sq.name AS `supplier_quotation`,
            DATE(sq.transaction_date) AS `sq_date`,
            sq.workflow_state AS `sq_status`,
            sq.grand_total AS `sq_total`,

            -- Purchase Order
            po.name AS `purchase_order`,
            DATE(po.transaction_date) AS `po_date`,
            po.supplier AS `po_supplier`,
            po.grand_total AS `po_total`,
            po.status AS `po_status`,

            -- Payment Information (will be calculated in Python)
            COALESCE(
                (SELECT GROUP_CONCAT(DISTINCT pe2.name SEPARATOR ', ')
                 FROM `tabPayment Entry Reference` per2
                 JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
                 WHERE per2.reference_name = po.name AND pe2.docstatus = 1
                 GROUP BY per2.reference_name), 
                NULL
            ) AS `payment_entries_raw`,
            
            COALESCE(
                (SELECT MIN(pe2.posting_date)
                 FROM `tabPayment Entry Reference` per2
                 JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
                 WHERE per2.reference_name = po.name AND pe2.docstatus = 1
                 GROUP BY per2.reference_name), 
                NULL
            ) AS `first_payment_date_raw`,
            
            COALESCE(
                (SELECT SUM(pe2.paid_amount)
                 FROM `tabPayment Entry Reference` per2
                 JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
                 WHERE per2.reference_name = po.name AND pe2.docstatus = 1
                 GROUP BY per2.reference_name), 
                0
            ) AS `total_paid_raw`

        FROM `tabMaterial Request` mr
        LEFT JOIN `tabMaterial Request Item` mri
            ON mri.parent = mr.name
        LEFT JOIN `tabSupplier Quotation Item` sqi
            ON sqi.material_request = mr.name
        LEFT JOIN `tabSupplier Quotation` sq
            ON sqi.parent = sq.name AND sq.docstatus = 1
        LEFT JOIN `tabPurchase Order Item` poi
            ON poi.material_request = mr.name
        LEFT JOIN `tabPurchase Order` po
            ON poi.parent = po.name AND po.docstatus = 1

        WHERE mr.docstatus = 1
    """

    # Add filters if provided
    conditions = []
    values = {}

    if filters:
        if filters.get('material_request'):
            conditions.append("mr.name LIKE %(material_request)s")
            values['material_request'] = f"%{filters['material_request']}%"
        
        if filters.get('project'):
            conditions.append("(mri.project LIKE %(project)s OR mr.custom_project_name LIKE %(project)s)")
            values['project'] = f"%{filters['project']}%"
        
        if filters.get('mr_status'):
            conditions.append("mr.status = %(mr_status)s")
            values['mr_status'] = filters['mr_status']
        
        if filters.get('po_status'):
            conditions.append("po.status = %(po_status)s")
            values['po_status'] = filters['po_status']
        
        if filters.get('supplier'):
            conditions.append("po.supplier LIKE %(supplier)s")
            values['supplier'] = f"%{filters['supplier']}%"
        
        if filters.get('from_date'):
            conditions.append("DATE(mr.transaction_date) >= %(from_date)s")
            values['from_date'] = filters['from_date']
        
        if filters.get('to_date'):
            conditions.append("DATE(mr.transaction_date) <= %(to_date)s")
            values['to_date'] = filters['to_date']

    if conditions:
        query += " AND " + " AND ".join(conditions)

    # Group by
    query += " GROUP BY mr.name, sq.name, po.name"

    try:
        # Execute query
        raw_data = frappe.db.sql(query, values, as_dict=True)
        
        # Process data to add calculated fields
        processed_data = []
        for row in raw_data:
            processed_row = process_row_data(row)
            processed_data.append(processed_row)
        
        # Apply sorting logic
        if sort_by:
            processed_data = sort_data(processed_data, sort_by)
        else:
            # Default sort by MR date descending
            processed_data = sorted(processed_data, key=lambda x: x.get('mr_date', ''), reverse=True)
        
        return {
            'status': 'success',
            'data': processed_data,
            'total_count': len(processed_data)
        }
        
    except Exception as e:
        frappe.log_error(f"Error in material request tracking: {str(e)}", "Material Request Tracking")
        return {
            'status': 'error',
            'message': str(e)
        }


def process_row_data(row):
    """Process each row to add calculated fields"""
    
    processed = dict(row)
    
    # Format payment entries
    processed['payment_entries'] = row.get('payment_entries_raw') or 'None'
    
    # Format first payment date
    first_payment_date = row.get('first_payment_date_raw')
    processed['first_payment_date'] = first_payment_date.strftime('%Y-%m-%d') if first_payment_date else None
    
    # Format total paid
    processed['total_paid'] = float(row.get('total_paid_raw') or 0)
    
    # Calculate MR → SQ Delay
    processed['mr_sq_delay_days'] = calculate_delay(
        row.get('mr_date'),
        row.get('sq_date')
    )
    
    # Calculate SQ → PO Delay
    processed['sq_po_delay_days'] = calculate_delay(
        row.get('sq_date'),
        row.get('po_date')
    )
    
    # Calculate PO → Payment Delay
    processed['po_payment_delay_days'] = calculate_delay(
        row.get('po_date'),
        row.get('first_payment_date_raw')
    )
    
    # Remove raw fields
    processed.pop('payment_entries_raw', None)
    processed.pop('first_payment_date_raw', None)
    processed.pop('total_paid_raw', None)
    
    return processed


def calculate_delay(start_date, end_date):
    """Calculate delay in days between two dates"""
    if not start_date or not end_date:
        return None
    
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    delta = end_date - start_date
    return delta.days


def sort_data(data, sort_by):
    """Sort data based on the specified option"""
    
    if sort_by == 'mr_date_first':
        return sorted(data, key=lambda x: (
            x.get('mr_date') or date.min,
            x.get('material_request') or ''
        ), reverse=True)
    
    elif sort_by == 'sq_date_first':
        return sorted(data, key=lambda x: (
            x.get('sq_date') or date.min,
            x.get('mr_date') or date.min
        ), reverse=True)
    
    elif sort_by == 'id_first':
        return sorted(data, key=lambda x: x.get('material_request') or '')
    
    elif sort_by == 'process':
        # Sort by process completion status
        def process_score(row):
            if row.get('payment_entries') != 'None' and row.get('total_paid', 0) > 0:
                return 1  # Fully paid
            elif row.get('purchase_order'):
                return 2  # PO created
            elif row.get('supplier_quotation'):
                return 3  # SQ created
            else:
                return 4  # Only MR
        
        return sorted(data, key=lambda x: (
            process_score(x),
            x.get('mr_date') or date.min
        ))
    
    return data


@frappe.whitelist()
def get_material_request_details(material_request_name):
    """
    Get detailed information for a specific material request
    """
    try:
        # Get the main tracking data
        query = """
            SELECT
                mr.name AS `material_request`,
                DATE(mr.transaction_date) AS `mr_date`,
                mr.transaction_date AS `mr_full_date`,
                COALESCE(mri.project, mr.custom_project_name) AS `project`,
                mr.status AS `mr_status`,

                -- Supplier Quotation
                sq.name AS `supplier_quotation`,
                DATE(sq.transaction_date) AS `sq_date`,
                sq.workflow_state AS `sq_status`,
                sq.grand_total AS `sq_total`,
                sq.supplier AS `sq_supplier`,

                -- Purchase Order
                po.name AS `purchase_order`,
                DATE(po.transaction_date) AS `po_date`,
                po.supplier AS `po_supplier`,
                po.grand_total AS `po_total`,
                po.status AS `po_status`,

                -- Payment summary
                COALESCE(
                    (SELECT MIN(pe2.posting_date)
                     FROM `tabPayment Entry Reference` per2
                     JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
                     WHERE per2.reference_name = po.name AND pe2.docstatus = 1), 
                    NULL
                ) AS `first_payment_date`,
                
                COALESCE(
                    (SELECT SUM(pe2.paid_amount)
                     FROM `tabPayment Entry Reference` per2
                     JOIN `tabPayment Entry` pe2 ON pe2.name = per2.parent 
                     WHERE per2.reference_name = po.name AND pe2.docstatus = 1), 
                    0
                ) AS `total_paid`

            FROM `tabMaterial Request` mr
            LEFT JOIN `tabMaterial Request Item` mri
                ON mri.parent = mr.name
            LEFT JOIN `tabSupplier Quotation Item` sqi
                ON sqi.material_request = mr.name
            LEFT JOIN `tabSupplier Quotation` sq
                ON sqi.parent = sq.name AND sq.docstatus = 1
            LEFT JOIN `tabPurchase Order Item` poi
                ON poi.material_request = mr.name
            LEFT JOIN `tabPurchase Order` po
                ON poi.parent = po.name AND po.docstatus = 1
            WHERE mr.docstatus = 1 AND mr.name = %s
            GROUP BY mr.name, sq.name, po.name
        """
        
        raw_data = frappe.db.sql(query, material_request_name, as_dict=True)
        
        if not raw_data:
            # Get basic MR info
            mr = frappe.get_doc("Material Request", material_request_name)
            basic_data = [{
                'material_request': mr.name,
                'mr_date': mr.transaction_date.date() if mr.transaction_date else None,
                'project': mr.custom_project_name if hasattr(mr, 'custom_project_name') else None,
                'mr_status': mr.status,
                'supplier_quotation': None,
                'sq_date': None,
                'sq_status': None,
                'sq_total': None,
                'purchase_order': None,
                'po_date': None,
                'po_supplier': None,
                'po_total': None,
                'po_status': None,
                'first_payment_date': None,
                'total_paid': 0
            }]
            raw_data = basic_data
        
        # Process the first row with full details
        processed_data = process_row_data(raw_data[0])
        
        # Get detailed payment entries
        if processed_data.get('purchase_order'):
            payment_details = frappe.db.sql("""
                SELECT 
                    pe.name AS payment_entry,
                    pe.posting_date AS payment_date,
                    pe.reference_no AS reference_number,
                    pe.paid_amount AS amount,
                    pe.mode_of_payment AS mode,
                    pe.remarks
                FROM `tabPayment Entry Reference` per
                JOIN `tabPayment Entry` pe ON pe.name = per.parent
                WHERE per.reference_name = %s AND pe.docstatus = 1
                ORDER BY pe.posting_date ASC
            """, processed_data['purchase_order'], as_dict=True)
            
            processed_data['payment_details'] = payment_details
        
        return {
            'status': 'success',
            'data': processed_data
        }
        
    except Exception as e:
        frappe.log_error(f"Error in material request details: {str(e)}", "Material Request Tracking")
        return {
            'status': 'error',
            'message': str(e)
        }


@frappe.whitelist()
def get_filter_options():
    """
    Get filter options for the API
    """
    try:
        # Get unique MR statuses
        mr_statuses = frappe.db.sql_list("""
            SELECT DISTINCT status 
            FROM `tabMaterial Request` 
            WHERE docstatus = 1 
            ORDER BY status
        """)
        
        # Get unique PO statuses
        po_statuses = frappe.db.sql_list("""
            SELECT DISTINCT status 
            FROM `tabPurchase Order` 
            WHERE docstatus = 1 
            ORDER BY status
        """)
        
        # Get unique projects
        projects = frappe.db.sql("""
            SELECT DISTINCT project 
            FROM `tabMaterial Request Item` 
            WHERE project IS NOT NULL AND project != ''
            UNION
            SELECT DISTINCT custom_project_name 
            FROM `tabMaterial Request` 
            WHERE custom_project_name IS NOT NULL AND custom_project_name != ''
            ORDER BY 1
        """)
        
        # Get unique suppliers
        suppliers = frappe.db.sql_list("""
            SELECT DISTINCT supplier 
            FROM `tabPurchase Order` 
            WHERE docstatus = 1 AND supplier IS NOT NULL
            ORDER BY supplier
        """)
        
        return {
            'status': 'success',
            'filters': {
                'mr_statuses': mr_statuses,
                'po_statuses': po_statuses,
                'projects': [p[0] for p in projects if p[0]],
                'suppliers': suppliers,
                'sort_options': [
                    {'value': 'mr_date_first', 'label': 'MR Date (Newest First)'},
                    {'value': 'sq_date_first', 'label': 'SQ Date (Newest First)'},
                    {'value': 'id_first', 'label': 'MR ID (A-Z)'},
                    {'value': 'process', 'label': 'Process Flow (Completed First)'}
                ]
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Error in getting filter options: {str(e)}", "Material Request Tracking")
        return {
            'status': 'error',
            'message': str(e)
        }


@frappe.whitelist()
def get_delay_analytics(filters=None):
    """
    Get analytics about delays
    """
    try:
        # Get all data first
        response = get_material_request_tracking(filters)
        
        if response['status'] != 'success':
            return response
        
        data = response['data']
        
        # Calculate statistics
        mr_sq_delays = [row['mr_sq_delay_days'] for row in data if row['mr_sq_delay_days'] is not None]
        sq_po_delays = [row['sq_po_delay_days'] for row in data if row['sq_po_delay_days'] is not None]
        po_payment_delays = [row['po_payment_delay_days'] for row in data if row['po_payment_delay_days'] is not None]
        
        analytics = {
            'mr_to_sq': {
                'avg_delay': sum(mr_sq_delays) / len(mr_sq_delays) if mr_sq_delays else 0,
                'max_delay': max(mr_sq_delays) if mr_sq_delays else 0,
                'min_delay': min(mr_sq_delays) if mr_sq_delays else 0,
                'count': len(mr_sq_delays)
            },
            'sq_to_po': {
                'avg_delay': sum(sq_po_delays) / len(sq_po_delays) if sq_po_delays else 0,
                'max_delay': max(sq_po_delays) if sq_po_delays else 0,
                'min_delay': min(sq_po_delays) if sq_po_delays else 0,
                'count': len(sq_po_delays)
            },
            'po_to_payment': {
                'avg_delay': sum(po_payment_delays) / len(po_payment_delays) if po_payment_delays else 0,
                'max_delay': max(po_payment_delays) if po_payment_delays else 0,
                'min_delay': min(po_payment_delays) if po_payment_delays else 0,
                'count': len(po_payment_delays)
            }
        }
        
        return {
            'status': 'success',
            'analytics': analytics
        }
        
    except Exception as e:
        frappe.log_error(f"Error in delay analytics: {str(e)}", "Material Request Tracking")
        return {
            'status': 'error',
            'message': str(e)
        }