# Sales Approval Workflow & Monthly Commission (AED)

A specialized Odoo module designed for trading companies to automate discount governance and calculate monthly salesperson commissions based on confirmed sales.

---

## Overview & Functional Specification

This module introduces automated discount approval tiers and monthly confirmed sales commission tracking:
1. **Quotation Creation**: Salespersons create quotations for customers.
2. **Salesperson Discretion**: A salesperson can grant up to a **5% discount** without requiring approval.
3. **Manager Approval**: Discounts **above 5% and up to 10%** require **Sales Manager** approval.
4. **Director Approval**: Discounts **above 10%** require **Sales Director** approval.
5. **Anti-Self-Approval**: A salesperson cannot approve their own quotation.
6. **Order Confirmation**: Once the quotation is approved, it can be confirmed into a Sales Order.
7. **Monthly Commission Calculation (AED)**:
   - Monthly confirmed sales below **AED 30,000** → **0%**
   - Monthly confirmed sales **AED 30,000 – 59,999** → **5%**
   - Monthly confirmed sales **AED 60,000 and above** → **7.5%**
8. **Management Visibility**: Dedicated reporting, pivot tables, and dashboard cards showing each salesperson's monthly confirmed sales volume and calculated commission.

---

## Workflow Overview

```
                      [ Create Quotation ]
                               |
                   Check Discount Percentage
                               |
       +-----------------------+-----------------------+
       |                                               |
  Discount <= 5%                                 Discount > 5%
       |                                               |
[ Direct Confirmation ]                        Approval Required
                                                       |
                             +-------------------------+-------------------------+
                             |                                                   |
                     5% < Discount <= 10%                                 Discount > 10%
                             |                                                   |
                 [ Waiting Manager Approval ]                       [ Waiting Director Approval ]
                             |                                                   |
                     Sales Manager Approves?                             Sales Director Approves?
                   (Self-Approval FORBIDDEN)                           (Self-Approval FORBIDDEN)
                             |                                                   |
                             +-------------------------+-------------------------+
                                                       |
                                                  [ Approved ]
                                                       |
                                              [ Confirm Order ]
                                                       |
                                        [ Order Added to Monthly Sales ]
                                                       |
                                         [ Commission Batch Calculation ]
```

---

## Commission Calculation Rules (AED)

| Sales Volume Tier | Monthly Confirmed Net Sales Range | Commission Rate |
| :--- | :--- | :--- |
| **Tier 1** | Under AED 30,000 | **0.0%** |
| **Tier 2** | AED 30,000 – AED 59,999.99 | **5.0%** |
| **Tier 3** | AED 60,000 and above | **7.5%** |

* Commission is calculated on the net untaxed sales amount of all orders in `sale` or `done` state within the calendar month.
* Automatic currency conversion standardizes multi-currency sales into **AED** using the exchange rate on the order date.

---

## Security Groups

* **Salesperson** (`sales_team.group_sale_salesman`): Can create quotations, submit for approval, view own monthly commission sheets.
* **Sales Manager** (`sales_team.group_sale_manager`): Can approve discounts between 5% and 10% on other salespersons' quotations, compute and approve monthly commission sheets.
* **Sales Director** (`sales_approval_commission.group_sale_director`): Inherits Sales Manager rights; authorized to approve discounts > 10%.

---

## Module Structure

```
sales_approval_commission/
├── __init__.py
├── __manifest__.py
├── README.md
├── data/
│   └── ir_sequence_data.xml
├── models/
│   ├── __init__.py
│   ├── sale_order.py
│   └── sale_monthly_commission.py
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── tests/
│   ├── __init__.py
│   └── test_sales_approval_commission.py
├── views/
│   ├── menu_views.xml
│   ├── sale_monthly_commission_views.xml
│   └── sale_order_views.xml
└── wizard/
    ├── __init__.py
    ├── sale_commission_compute_wizard.py
    ├── sale_commission_compute_wizard_views.xml
    ├── sale_order_reject_wizard.py
    └── sale_order_reject_wizard_views.xml
```

---

## Installation & Testing

1. Place the module in your Odoo `custom_addons` path.
2. Update the Apps list in Odoo:
   ```bash
   python3 odoo-bin -u sales_approval_commission -d <your_database> --stop-after-init
   ```
3. Run the automated test suite:
   ```bash
   python3 odoo-bin --test-enable -i sales_approval_commission -d <your_database> --stop-after-init
   ```
