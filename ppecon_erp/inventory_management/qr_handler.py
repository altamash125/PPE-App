
import frappe
from frappe.utils import now
from io import BytesIO
import qrcode
from frappe.utils.file_manager import save_file
import base64

def generate_inventory_qr(doc, method=None):
    """
    Auto-generate QR code for Inventory Management
    """
    # Only process Inventory Management
    if doc.doctype != "Inventory Management":
        return
    
    # Skip if item_code is missing
    if not doc.item_code:
        frappe.msgprint("Item Code is required for QR generation", alert=True)
        return
    
    try:
        # Check if QR already exists
        if doc.item_qr and not getattr(doc, 'flags', {}).get('force_qr_regenerate', False):
            # Check if key fields changed
            if not should_regenerate_qr(doc):
                return
        
        frappe.log_error(f"Generating QR for {doc.item_code}", "QR Handler")
        
        # Generate QR content (SHORTER VERSION)
        qr_content = generate_qr_content(doc)
        
        # Create QR image
        qr_image = create_qr_image(qr_content)
        
        # Save as attachment
        file_url = attach_qr_to_doc(doc, qr_image, qr_content)
        
        # Store only essential data in qr_code field (not base64)
        # OPTION A: Store minimal data
        qr_data_for_db = f"{doc.item_code}|{now()}"
        
        # OPTION B: Store shortened text (max 255 chars)
        short_qr_data = qr_content[:200] if len(qr_content) > 200 else qr_content
        
        # Update the document field
        update_data = {
            'item_qr': file_url
        }
        
        # Only add qr_code if field exists and we want to store something
        if hasattr(doc, 'qr_code'):
            update_data['qr_code'] = short_qr_data  # Store plain text, not base64
        
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            update_data
        )
        
        frappe.db.commit()
        
        frappe.msgprint(f"QR Code generated for {doc.item_code}", indicator="green", alert=True)
        
    except Exception as e:
        frappe.log_error(f"QR Generation Error for {doc.item_code}: {str(e)}", "Inventory QR")
        frappe.msgprint(f"QR Generation Failed: {str(e)}", indicator="red", alert=True)

def should_regenerate_qr(doc):
    """Check if QR should be regenerated"""
    previous = doc.get_doc_before_save()
    if not previous:
        return False
    
    key_fields = ['item_code', 'item_description', 'groups', 'category', 'date_of_purchase']
    
    for field in key_fields:
        current = getattr(doc, field, None)
        previous_val = getattr(previous, field, None)
        if (current or "") != (previous_val or ""):
            return True
    
    return False

def generate_qr_content(doc):
    """Generate QR text content - SHORTER VERSION"""
    # Create a more compact QR content
    content = f"""Item:{doc.item_code or ''}
Desc:{doc.item_description[:50] if doc.item_description else ''}
Grp:{doc.groups or ''}
Cat:{doc.category or ''}
Date:{doc.date_of_purchase or ''}"""
    
    return content[:500]  # Limit to 500 characters

def create_qr_image(qr_code):
    """Create QR image from text"""
    qr = qrcode.QRCode(
        version=None,  # Auto-select version
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,  # Smaller box size
        border=2,    # Smaller border
    )
    qr.add_data(qr_code)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#000000", back_color="#FFFFFF")
    
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    
    return buf.getvalue()

def attach_qr_to_doc(doc, qr_bytes, qr_code):
    """Attach QR code to document"""
    # Delete existing QR files
    delete_existing_qr(doc)
    
    # Generate filename
    filename = f"{doc.item_code.replace(' ', '_')}_QR.png"
    
    # Save the file
    file_doc = save_file(
        fname=filename,
        content=qr_bytes,
        dt=doc.doctype,
        dn=doc.name,
        folder="Home/Attachments",
        is_private=0,
        decode=False
    )
    
    frappe.log_error(f"QR saved: {file_doc.file_url}", "QR Handler")
    return file_doc.file_url

def delete_existing_qr(doc):
    """Delete existing QR attachments"""
    try:
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": doc.doctype,
                "attached_to_name": doc.name,
                "file_name": ["like", "%QR%"]
            },
            fields=["name"]
        )
        
        for file in files:
            frappe.delete_doc("File", file.name, ignore_permissions=True, force=True)
            
    except Exception as e:
        frappe.log_error(f"Error deleting old QR: {str(e)}", "QR Handler")