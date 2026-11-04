
from odoo import _, api, fields, models


class SaleCommissionComputeWizard(models.TransientModel):
    _name = 'sale.commission.compute.wizard'
    _description = 'Batch Compute Monthly Sales Commissions'

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
    )
    year = fields.Integer(
        string="Year",
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    compute_all_salespersons = fields.Boolean(
        string="All Active Salespersons",
        default=True,
        help="If checked, calculates commission for all salespersons who have confirmed orders or are in the sales team.",
    )
    salesperson_ids = fields.Many2many(
        'res.users',
        string="Specific Salespersons",
        help="Select specific salespersons to compute commissions for.",
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.onchange('compute_all_salespersons')
    def _onchange_compute_all_salespersons(self):
        if self.compute_all_salespersons:
            self.salesperson_ids = False

    def action_batch_compute(self):
        """Batch compute monthly commissions for specified salespersons."""
        self.ensure_one()
        commission_obj = self.env['sale.monthly.commission']

        if self.compute_all_salespersons:
            # Salespersons with confirmed orders in this month or members of sales teams
            start_dt = f"{self.year}-{self.month}-01 00:00:00"
            salesmen = self.env['sale.order'].search([
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>=', start_dt),
                ('company_id', '=', self.company_id.id),
                ('user_id', '!=', False),
            ]).mapped('user_id')

            # Also include users who are sales representatives
            salesman_group = self.env.ref('sales_team.group_sale_salesman', raise_if_not_found=False)
            team_members = (
                salesman_group.all_user_ids or salesman_group.user_ids
            ).filtered(lambda u: not u.share and u.active) if salesman_group else self.env['res.users']
            target_salespersons = salesmen | team_members
        else:
            target_salespersons = self.salesperson_ids

        result_commissions = commission_obj.browse()

        for sp in target_salespersons:
            # Check if record already exists
            comm_sheet = commission_obj.search([
                ('salesperson_id', '=', sp.id),
                ('month', '=', self.month),
                ('year', '=', self.year),
                ('company_id', '=', self.company_id.id),
            ], limit=1)

            if not comm_sheet:
                comm_sheet = commission_obj.create({
                    'salesperson_id': sp.id,
                    'month': self.month,
                    'year': self.year,
                    'company_id': self.company_id.id,
                })

            if comm_sheet.state not in ('approved', 'paid'):
                comm_sheet.action_compute_commission()

            result_commissions |= comm_sheet

        return {
            'name': _("Monthly Commissions (%s/%s)") % (self.month, self.year),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.monthly.commission',
            'view_mode': 'pivot,list,form,graph',
            'domain': [('id', 'in', result_commissions.ids)],
            'context': {
                'search_default_group_by_salesperson': 1,
            },
        }
