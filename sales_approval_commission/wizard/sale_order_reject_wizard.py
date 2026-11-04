
from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrderRejectWizard(models.TransientModel):
    _name = 'sale.order.reject.wizard'
    _description = 'Reject Quotation Discount'

    order_id = fields.Many2one(
        'sale.order',
        string="Quotation",
        required=True,
        readonly=True,
    )
    rejection_reason = fields.Text(
        string="Reason for Rejection",
        required=True,
        help="State why the requested discount level was rejected.",
    )

    def action_confirm_rejection(self):
        """Confirm rejection with validation and chatter logging."""
        self.ensure_one()
        order = self.order_id

        is_director = self.env.user.has_group('sales_approval_commission.group_sale_director')
        if order.user_id and order.user_id == self.env.user and not is_director:
            raise UserError(_("You cannot reject your own quotation. An independent approver must review it."))

        # Check permissions
        if order.approval_state == 'waiting_director':
            if not self.env.user.has_group('sales_approval_commission.group_sale_director'):
                raise UserError(_("Only a Sales Director can review or reject this quotation."))
        elif order.approval_state == 'waiting_manager':
            if not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_("Only a Sales Manager or Director can review or reject this quotation."))

        order.write({
            'approval_state': 'rejected',
            'rejection_reason': self.rejection_reason,
            'approved_by_id': False,
            'approval_date': False,
        })

        order.message_post(
            body=_(
                "Quotation discount (%.2f%%) was <b>REJECTED</b> by <b>%s</b>.<br/>"
                "<b>Reason:</b> %s",
            ) % (order.highest_discount, self.env.user.name, self.rejection_reason),
        )
        return {'type': 'ir.actions.act_window_close'}
