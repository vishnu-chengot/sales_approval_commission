
from datetime import datetime

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalesApprovalCommission(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Groups
        cls.group_salesman = cls.env.ref('sales_team.group_sale_salesman')
        cls.group_manager = cls.env.ref('sales_team.group_sale_manager')
        cls.group_director = cls.env.ref('sales_approval_commission.group_sale_director')

        # AED Currency setup
        cls.currency_aed = cls.env['res.currency'].search([('name', '=', 'AED')], limit=1)
        if not cls.currency_aed:
            cls.currency_aed = cls.env['res.currency'].create({
                'name': 'AED',
                'symbol': 'AED',
                'rounding': 0.01,
                'active': True,
            })
        else:
            cls.currency_aed.active = True

        # Test Users
        cls.salesperson_user = cls.env['res.users'].create({
            'name': 'Sales Rep John',
            'login': 'sales_rep_john',
            'email': 'sales_rep_john@tradingcompany.com',
            'group_ids': [(6, 0, [cls.group_salesman.id])],
        })

        cls.manager_user = cls.env['res.users'].create({
            'name': 'Sales Manager Sarah',
            'login': 'sales_mgr_sarah',
            'email': 'sales_mgr_sarah@tradingcompany.com',
            'group_ids': [(6, 0, [cls.group_manager.id])],
        })

        cls.director_user = cls.env['res.users'].create({
            'name': 'Sales Director David',
            'login': 'sales_dir_david',
            'email': 'sales_dir_david@tradingcompany.com',
            'group_ids': [(6, 0, [cls.group_director.id])],
        })

        # Test Partner & Product
        cls.customer = cls.env['res.partner'].create({
            'name': 'Customer Gulf Trading LLC',
        })

        cls.product = cls.env['product.product'].create({
            'name': 'Standard Trading Unit',
            'list_price': 1000.0,
            'type': 'service',
        })

    def _create_quotation(self, user, discount, qty=1.0, price_unit=1000.0, date_order=None):
        """Helper to create quotation with specified discount and salesperson."""
        vals = {
            'partner_id': self.customer.id,
            'user_id': user.id,
            'currency_id': self.currency_aed.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_uom_qty': qty,
                    'price_unit': price_unit,
                    'discount': discount,
                }),
            ],
        }
        if date_order:
            vals['date_order'] = date_order
        return self.env['sale.order'].create(vals)

    # -------------------------------------------------------------------------
    # TEST 1: Max 5% discount can confirm WITHOUT approval
    # -------------------------------------------------------------------------
    def test_01_discount_under_or_equal_5_percent_no_approval_needed(self):
        """Salesperson can give up to 5% discount and confirm without approval."""
        order = self._create_quotation(self.salesperson_user, discount=5.0)
        self.assertEqual(order.highest_discount, 5.0)
        self.assertFalse(order.requires_approval)
        self.assertEqual(order.approval_type, 'none')

        # Direct confirmation should succeed without error
        order.with_user(self.salesperson_user).action_confirm()
        self.assertEqual(order.state, 'sale')

    # -------------------------------------------------------------------------
    # TEST 2: Discount between 5% and 10% requires Sales Manager approval
    # -------------------------------------------------------------------------
    def test_02_discount_between_5_and_10_percent_requires_manager(self):
        """Discounts above 5% and up to 10% require Sales Manager approval."""
        order = self._create_quotation(self.salesperson_user, discount=8.0)
        self.assertEqual(order.highest_discount, 8.0)
        self.assertTrue(order.requires_approval)
        self.assertEqual(order.approval_type, 'manager')

        # Confirmation before approval must be blocked
        with self.assertRaises(UserError):
            order.with_user(self.salesperson_user).action_confirm()

        # Submit for approval
        order.with_user(self.salesperson_user).action_submit_approval()
        self.assertEqual(order.approval_state, 'waiting_manager')

    # -------------------------------------------------------------------------
    # TEST 3: Discount above 10% requires Sales Director approval
    # -------------------------------------------------------------------------
    def test_03_discount_above_10_percent_requires_director(self):
        """Discounts above 10% require Sales Director approval."""
        order = self._create_quotation(self.salesperson_user, discount=15.0)
        self.assertEqual(order.highest_discount, 15.0)
        self.assertTrue(order.requires_approval)
        self.assertEqual(order.approval_type, 'director')

        # Confirmation before approval must be blocked
        with self.assertRaises(UserError):
            order.with_user(self.salesperson_user).action_confirm()

        # Submit for approval
        order.with_user(self.salesperson_user).action_submit_approval()
        self.assertEqual(order.approval_state, 'waiting_director')

    # -------------------------------------------------------------------------
    # TEST 4: Anti-Self-Approval rule enforcement
    # -------------------------------------------------------------------------
    def test_04_salesperson_cannot_approve_own_quotation(self):
        """A salesperson should not be able to approve their own quotation."""
        order = self._create_quotation(self.manager_user, discount=8.0)
        order.action_submit_approval()
        self.assertEqual(order.approval_state, 'waiting_manager')

        # Even though manager_user has manager rights, they are the salesperson on this order!
        with self.assertRaises(UserError) as cm:
            order.with_user(self.manager_user).action_approve()
        self.assertIn("cannot approve your own quotation", str(cm.exception))

    # -------------------------------------------------------------------------
    # TEST 5: Manager approves 8% quotation, then it can be confirmed
    # -------------------------------------------------------------------------
    def test_05_manager_approval_and_subsequent_confirmation(self):
        """Sales Manager approves quotation, allowing confirmation."""
        order = self._create_quotation(self.salesperson_user, discount=8.0)
        order.with_user(self.salesperson_user).action_submit_approval()

        # Manager approves
        order.with_user(self.manager_user).action_approve()
        self.assertEqual(order.approval_state, 'approved')
        self.assertEqual(order.approved_by_id, self.manager_user)

        # Salesperson confirms approved order
        order.with_user(self.salesperson_user).action_confirm()
        self.assertEqual(order.state, 'sale')

    # -------------------------------------------------------------------------
    # TEST 6: Manager cannot approve > 10% quotation (requires Director)
    # -------------------------------------------------------------------------
    def test_06_manager_cannot_approve_director_tier(self):
        """Manager without Director permissions cannot approve discounts > 10%."""
        order = self._create_quotation(self.salesperson_user, discount=12.0)
        order.with_user(self.salesperson_user).action_submit_approval()
        self.assertEqual(order.approval_state, 'waiting_director')

        # Sales Manager tries to approve > 10% discount -> must fail
        with self.assertRaises(UserError):
            order.with_user(self.manager_user).action_approve()

        # Sales Director approves -> succeeds
        order.with_user(self.director_user).action_approve()
        self.assertEqual(order.approval_state, 'approved')

        # Confirmation succeeds
        order.with_user(self.salesperson_user).action_confirm()
        self.assertEqual(order.state, 'sale')

    # -------------------------------------------------------------------------
    # TEST 7: Rejection workflow
    # -------------------------------------------------------------------------
    def test_07_quotation_rejection_workflow(self):
        """Approver can reject discount, blocking confirmation until adjusted."""
        order = self._create_quotation(self.salesperson_user, discount=9.0)
        order.with_user(self.salesperson_user).action_submit_approval()

        # Reject via wizard
        wizard = self.env['sale.order.reject.wizard'].with_user(self.manager_user).create({
            'order_id': order.id,
            'rejection_reason': 'Margin too thin for this contract size.',
        })
        wizard.action_confirm_rejection()

        self.assertEqual(order.approval_state, 'rejected')
        self.assertEqual(order.rejection_reason, 'Margin too thin for this contract size.')

        # Attempt to confirm must fail
        with self.assertRaises(UserError):
            order.with_user(self.salesperson_user).action_confirm()

    # -------------------------------------------------------------------------
    # TEST 8: Monthly Commission Tier 1: Below AED 30,000 -> 0%
    # -------------------------------------------------------------------------
    def test_08_commission_tier_1_below_30k_gives_0_percent(self):
        """Monthly confirmed sales below AED 30,000 yields 0% commission."""
        order_date = datetime(2026, 11, 10, 10, 0, 0)
        # 25,000 AED sales
        order = self._create_quotation(self.salesperson_user, discount=0.0, qty=25.0, price_unit=1000.0, date_order=order_date)
        order.action_confirm()

        comm_sheet = self.env['sale.monthly.commission'].create({
            'salesperson_id': self.salesperson_user.id,
            'month': '11',
            'year': 2026,
        })
        comm_sheet.action_compute_commission()

        self.assertEqual(comm_sheet.total_confirmed_sales, 25000.0)
        self.assertEqual(comm_sheet.tier_applied, 'tier_1')
        self.assertEqual(comm_sheet.commission_rate, 0.0)
        self.assertEqual(comm_sheet.commission_amount, 0.0)

    # -------------------------------------------------------------------------
    # TEST 9: Monthly Commission Tier 2: AED 30,000 - 59,999 -> 5%
    # -------------------------------------------------------------------------
    def test_09_commission_tier_2_between_30k_and_60k_gives_5_percent(self):
        """Monthly confirmed sales AED 30,000 - 59,999 yields 5% commission."""
        order_date = datetime(2026, 11, 12, 10, 0, 0)
        # 40,000 AED sales
        order = self._create_quotation(self.salesperson_user, discount=0.0, qty=40.0, price_unit=1000.0, date_order=order_date)
        order.action_confirm()

        comm_sheet = self.env['sale.monthly.commission'].create({
            'salesperson_id': self.salesperson_user.id,
            'month': '11',
            'year': 2026,
        })
        comm_sheet.action_compute_commission()

        self.assertEqual(comm_sheet.total_confirmed_sales, 40000.0)
        self.assertEqual(comm_sheet.tier_applied, 'tier_2')
        self.assertEqual(comm_sheet.commission_rate, 5.0)
        # 40,000 * 5% = 2,000 AED
        self.assertEqual(comm_sheet.commission_amount, 2000.0)

    # -------------------------------------------------------------------------
    # TEST 10: Monthly Commission Tier 3: AED 60,000 and above -> 7.5%
    # -------------------------------------------------------------------------
    def test_10_commission_tier_3_above_60k_gives_7_point_5_percent(self):
        """Monthly confirmed sales AED 60,000 and above yields 7.5% commission."""
        order_date_1 = datetime(2026, 11, 5, 10, 0, 0)
        order_date_2 = datetime(2026, 11, 15, 10, 0, 0)
        # Order 1: 50,000 AED
        order1 = self._create_quotation(self.salesperson_user, discount=0.0, qty=50.0, price_unit=1000.0, date_order=order_date_1)
        order1.action_confirm()

        # Order 2: 30,000 AED (Total: 80,000 AED)
        order2 = self._create_quotation(self.salesperson_user, discount=0.0, qty=30.0, price_unit=1000.0, date_order=order_date_2)
        order2.action_confirm()

        comm_sheet = self.env['sale.monthly.commission'].create({
            'salesperson_id': self.salesperson_user.id,
            'month': '11',
            'year': 2026,
        })
        comm_sheet.action_compute_commission()

        self.assertEqual(comm_sheet.confirmed_order_count, 2)
        self.assertEqual(comm_sheet.total_confirmed_sales, 80000.0)
        self.assertEqual(comm_sheet.tier_applied, 'tier_3')
        self.assertEqual(comm_sheet.commission_rate, 7.5)
        # 80,000 * 7.5% = 6,000 AED
        self.assertEqual(comm_sheet.commission_amount, 6000.0)

        # Test manager approval and pay workflow
        comm_sheet.with_user(self.manager_user).action_approve()
        self.assertEqual(comm_sheet.state, 'approved')
        comm_sheet.with_user(self.manager_user).action_pay()
        self.assertEqual(comm_sheet.state, 'paid')

    # -------------------------------------------------------------------------
    # TEST 11: Sales Director executive approval authority
    # -------------------------------------------------------------------------
    def test_11_sales_director_can_approve_executive_quotation(self):
        """Sales Director holds executive authority and can approve quotations."""
        order = self._create_quotation(self.director_user, discount=12.0)
        order.with_user(self.director_user).action_submit_approval()
        order.with_user(self.director_user).action_approve()
        self.assertEqual(order.approval_state, 'approved')
        order.with_user(self.director_user).action_confirm()
        self.assertEqual(order.state, 'sale')
