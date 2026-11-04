{
    'name': 'Sales Approval Workflow & Monthly Commission',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Multi-tier discount approval workflow and salesperson monthly commission calculation (AED)',
    'description': """
Sales Approval Workflow & Monthly Sales Commission
==================================================

This module provides business process controls and commission tracking for trading companies:

Key Features:
-------------
1. **Multi-Tier Discount Approval Workflow**:
   * Up to 5% discount: Quotations can be confirmed directly by the salesperson without approval.
   * Discounts > 5% and up to 10%: Requires approval from a **Sales Manager**.
   * Discounts > 10%: Requires approval from a **Sales Director**.
   * **Strict Anti-Self-Approval**: A salesperson cannot approve their own quotation under any circumstances.
   * Quotations requiring approval cannot be confirmed until authorized.

2. **Monthly Salesperson Commission Calculation (AED)**:
   * Automatic calculation based on confirmed sales within each calendar month:
     - Confirmed sales below AED 30,000  ->  0% commission
     - Confirmed sales AED 30,000–59,999 ->  5% commission
     - Confirmed sales AED 60,000+       ->  7.5% commission
   * Currency-aware conversion into AED if transactions are processed in other currencies.
   * Dedicated management reporting with tree, form, pivot, and graph views.
   * Batch generation wizard for managers to compute monthly commissions across all salespersons.
   * Detailed breakdown linking every confirmed sales order to the monthly commission sheet.
    """,
    'author': 'vishnuchengot',
    'website': 'https://www.odoo.com',
    'depends': [
        'sale',
        'sales_team',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'wizard/sale_order_reject_wizard_views.xml',
        'wizard/sale_commission_compute_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/sale_monthly_commission_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
