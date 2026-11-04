
import calendar
from datetime import date, datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleMonthlyCommission(models.Model):
    _name = 'sale.monthly.commission'
    _description = 'Monthly Salesperson Commission (AED)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, salesperson_id asc'

    name = fields.Char(
        string="Reference",
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
    )
    salesperson_id = fields.Many2one(
        'res.users',
        string="Salesperson",
        required=True,
        tracking=True,
        index=True,
        default=lambda self: self.env.user,
        help="The salesperson whose monthly sales and commission are being calculated.",
    )
    month = fields.Selection(
        [
            ('01', 'January'),
            ('02', 'February'),
            ('03', 'March'),
            ('04', 'April'),
            ('05', 'May'),
            ('06', 'June'),
            ('07', 'July'),
            ('08', 'August'),
            ('09', 'September'),
            ('10', 'October'),
            ('11', 'November'),
            ('12', 'December'),
        ],
        string="Month",
        required=True,
        default=lambda self: fields.Date.today().strftime('%m'),
        tracking=True,
    )
    year = fields.Integer(
        string="Year",
        required=True,
        default=lambda self: fields.Date.today().year,
        tracking=True,
    )
    date_from = fields.Date(
        string="Period Start",
        compute="_compute_period_dates",
        store=True,
        help="Start date of the sales calculation month.",
    )
    date_to = fields.Date(
        string="Period End",
        compute="_compute_period_dates",
        store=True,
        help="End date of the sales calculation month.",
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Commission Currency",
        compute="_compute_commission_currency",
        store=True,
        help="Commission amounts are standardized to AED.",
    )
    order_line_ids = fields.One2many(
        'sale.monthly.commission.line',
        'commission_id',
        string="Confirmed Sales Breakdown",
        copy=False,
    )
    confirmed_order_count = fields.Integer(
        string="Confirmed Orders",
        compute="_compute_commission_totals",
        store=True,
        help="Number of confirmed sales orders in this period.",
    )
    total_confirmed_sales = fields.Monetary(
        string="Monthly Confirmed Sales (AED)",
        compute="_compute_commission_totals",
        store=True,
        currency_field='currency_id',
        tracking=True,
        help="Total net sales value of confirmed orders converted to AED.",
    )
    tier_applied = fields.Selection(
        [
            ('tier_1', 'Tier 1: Below AED 30,000 (0% Rate)'),
            ('tier_2', 'Tier 2: AED 30,000 – 59,999 (5% Rate)'),
            ('tier_3', 'Tier 3: AED 60,000 and above (7.5% Rate)'),
        ],
        string="Commission Tier",
        compute="_compute_commission_totals",
        store=True,
        tracking=True,
        help="Commission tier applied according to monthly sales volume.",
    )
    commission_rate = fields.Float(
        string="Commission Rate (%)",
        compute="_compute_commission_totals",
        store=True,
        digits=(16, 2),
        tracking=True,
        help="Applicable commission rate: 0%, 5%, or 7.5%.",
    )
    commission_amount = fields.Monetary(
        string="Calculated Commission (AED)",
        compute="_compute_commission_totals",
        store=True,
        currency_field='currency_id',
        tracking=True,
        help="Final calculated commission amount payable in AED.",
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('calculated', 'Calculated'),
            ('approved', 'Approved'),
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        string="Status",
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    calculation_date = fields.Datetime(
        string="Calculated On",
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string="Notes")

    _sql_constraints = [
        (
            'unique_salesperson_month_year',
            'unique(salesperson_id, month, year, company_id)',
            'A monthly commission record already exists for this salesperson, month, and year.',
        ),
    ]

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('month', 'year')
    def _compute_period_dates(self):
        for record in self:
            if record.month and record.year:
                m = int(record.month)
                y = record.year
                last_day = calendar.monthrange(y, m)[1]
                record.date_from = date(y, m, 1)
                record.date_to = date(y, m, last_day)
            else:
                record.date_from = False
                record.date_to = False

    @api.depends('company_id')
    def _compute_commission_currency(self):
        for record in self:
            aed = self.env['res.currency'].search([('name', '=', 'AED')], limit=1)
            if aed:
                record.currency_id = aed
            else:
                record.currency_id = record.company_id.currency_id

    @api.depends('order_line_ids.sales_amount_aed')
    def _compute_commission_totals(self):
        for record in self:
            order_count = len(record.order_line_ids)
            total_sales = sum(line.sales_amount_aed for line in record.order_line_ids)

            # Monthly confirmed sales tiers:
            # Below AED 30,000 -> 0%
            # AED 30,000 - 59,999 -> 5%
            # AED 60,000 and above -> 7.5%
            if total_sales < 30000.0:
                tier = 'tier_1'
                rate = 0.0
            elif total_sales < 60000.0:
                tier = 'tier_2'
                rate = 5.0
            else:
                tier = 'tier_3'
                rate = 7.5

            comm_amount = total_sales * (rate / 100.0)

            record.confirmed_order_count = order_count
            record.total_confirmed_sales = total_sales
            record.tier_applied = tier
            record.commission_rate = rate
            record.commission_amount = comm_amount

    # -------------------------------------------------------------------------
    # CRUD OVERRIDES
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_date = None
                if vals.get('year') and vals.get('month'):
                    seq_date = f"{vals['year']}-{vals['month']}-01"
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.monthly.commission',
                    sequence_date=seq_date,
                ) or _('New')
        return super().create(vals_list)

    @api.constrains('year')
    def _check_year(self):
        for record in self:
            if record.year < 2000 or record.year > 2100:
                raise ValidationError(_("Please provide a valid 4-digit year between 2000 and 2100."))

    # -------------------------------------------------------------------------
    # ACTIONS & CALCULATION ENGINE
    # -------------------------------------------------------------------------
    def action_compute_commission(self):
        """Fetch confirmed sales orders for this salesperson in the month and calculate commission."""
        for record in self:
            if record.state in ('approved', 'paid'):
                raise UserError(_("Cannot recalculate an approved or paid commission sheet."))

            if not record.date_from or not record.date_to:
                record._compute_period_dates()

            start_dt = datetime.combine(record.date_from, time.min)
            end_dt = datetime.combine(record.date_to, time.max)

            # Find all confirmed sales orders for this salesperson in this period
            orders = self.env['sale.order'].search([
                ('user_id', '=', record.salesperson_id.id),
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>=', start_dt),
                ('date_order', '<=', end_dt),
                ('company_id', '=', record.company_id.id),
            ])

            # Prepare commission currency (standardized to AED)
            aed_currency = record.currency_id or self.env['res.currency'].search([('name', '=', 'AED')], limit=1) or record.company_id.currency_id

            # Rebuild commission breakdown lines
            record.order_line_ids.unlink()

            new_lines = []
            for order in orders:
                # Convert untaxed sales amount to AED currency
                if order.currency_id and order.currency_id != aed_currency:
                    converted_aed = order.currency_id._convert(
                        order.amount_untaxed,
                        aed_currency,
                        order.company_id,
                        order.date_order.date() if order.date_order else fields.Date.today(),
                    )
                else:
                    converted_aed = order.amount_untaxed

                new_lines.append((0, 0, {
                    'commission_id': record.id,
                    'order_id': order.id,
                    'sales_amount_aed': converted_aed,
                }))

            record.write({
                'order_line_ids': new_lines,
                'calculation_date': fields.Datetime.now(),
                'state': 'calculated',
            })

            record.message_post(
                body=_(
                    "Commission computed for <b>%s</b>.<br/>"
                    "Confirmed Orders: <b>%d</b><br/>"
                    "Total Confirmed Sales: <b>%.2f AED</b><br/>"
                    "Commission Rate: <b>%.1f%%</b><br/>"
                    "Calculated Commission: <b>%.2f AED</b>",
                ) % (
                    record.salesperson_id.name,
                    record.confirmed_order_count,
                    record.total_confirmed_sales,
                    record.commission_rate,
                    record.commission_amount,
                ),
            )

    def action_approve(self):
        """Manager approves the calculated commission sheet."""
        for record in self:
            if record.state != 'calculated':
                raise UserError(_("Only calculated commission sheets can be approved."))
            record.write({'state': 'approved'})
            record.message_post(body=_("Monthly commission approved by %s.") % self.env.user.name)

    def action_pay(self):
        """Mark commission as paid."""
        for record in self:
            if record.state != 'approved':
                raise UserError(_("Commission sheet must be approved before marking as paid."))
            record.write({'state': 'paid'})
            record.message_post(body=_("Monthly commission marked as Paid by %s.") % self.env.user.name)

    def action_cancel(self):
        """Cancel commission sheet."""
        for record in self:
            if record.state == 'paid':
                raise UserError(_("Cannot cancel a commission sheet that has already been paid."))
            record.write({'state': 'cancelled'})
            record.message_post(body=_("Monthly commission cancelled by %s.") % self.env.user.name)

    def action_reset_draft(self):
        """Reset commission sheet to Draft."""
        for record in self:
            if record.state == 'paid':
                raise UserError(_("Cannot reset a paid commission sheet to draft."))
            record.write({'state': 'draft'})
            record.message_post(body=_("Monthly commission reset to Draft."))

    def action_view_orders(self):
        """Open confirmed sales orders included in this commission sheet."""
        self.ensure_one()
        order_ids = self.order_line_ids.mapped('order_id').ids
        return {
            'name': _("Confirmed Orders - %s (%s/%s)") % (self.salesperson_id.name, self.month, self.year),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', order_ids)],
            'context': {'create': False},
        }


class SaleMonthlyCommissionLine(models.Model):
    _name = 'sale.monthly.commission.line'
    _description = 'Monthly Commission Order Line'
    _order = 'date_order desc'

    commission_id = fields.Many2one(
        'sale.monthly.commission',
        string="Commission Sheet",
        required=True,
        ondelete='cascade',
        index=True,
    )
    order_id = fields.Many2one(
        'sale.order',
        string="Sales Order",
        required=True,
        ondelete='restrict',
        index=True,
    )
    order_name = fields.Char(
        related='order_id.name',
        string="Order Reference",
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='order_id.partner_id',
        string="Customer",
        readonly=True,
    )
    date_order = fields.Datetime(
        related='order_id.date_order',
        string="Order Date",
        readonly=True,
    )
    order_currency_id = fields.Many2one(
        related='order_id.currency_id',
        string="Order Currency",
        readonly=True,
    )
    order_amount_untaxed = fields.Monetary(
        related='order_id.amount_untaxed',
        currency_field='order_currency_id',
        string="Untaxed Total",
        readonly=True,
    )
    order_amount_total = fields.Monetary(
        related='order_id.amount_total',
        currency_field='order_currency_id',
        string="Order Total",
        readonly=True,
    )
    sales_amount_aed = fields.Monetary(
        string="Sales in AED",
        required=True,
        currency_field='currency_id',
        help="Net untaxed sales amount converted to AED on the date of order confirmation.",
    )
    currency_id = fields.Many2one(
        related='commission_id.currency_id',
        string="Currency",
        readonly=True,
    )
