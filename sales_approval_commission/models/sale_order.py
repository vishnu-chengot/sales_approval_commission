
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    max_discount = fields.Float(
        string="Max Line Discount (%)",
        compute="_compute_discount_details",
        store=True,
        digits=(16, 2),
        help="Maximum discount percentage applied to any individual order line.",
    )
    total_discount_amount = fields.Monetary(
        string="Total Discount Amount",
        compute="_compute_discount_details",
        store=True,
        currency_field='currency_id',
        help="Calculated total monetary value of all line discounts.",
    )
    effective_discount_rate = fields.Float(
        string="Effective Discount Rate (%)",
        compute="_compute_discount_details",
        store=True,
        digits=(16, 2),
        help="Weighted average discount percentage across the entire quotation.",
    )
    highest_discount = fields.Float(
        string="Governing Discount (%)",
        compute="_compute_discount_details",
        store=True,
        digits=(16, 2),
        help="The governing discount percentage (max of line discount and effective rate) used for approval evaluation.",
    )
    global_discount = fields.Float(
        string="Overall Discount (%)",
        digits=(16, 2),
        copy=False,
        help="Enter a discount percentage to apply uniformly across all quotation lines.",
    )
    approval_type = fields.Selection(
        [
            ('none', 'No Approval Required (<= 5%)'),
            ('manager', 'Sales Manager Approval Required (5% - 10%)'),
            ('director', 'Sales Director Approval Required (> 10%)'),
        ],
        string="Approval Requirement",
        compute="_compute_approval_type",
        store=True,
        tracking=True,
        help="Indicates whether this quotation requires manager or director authorization.",
    )
    requires_approval = fields.Boolean(
        string="Requires Approval",
        compute="_compute_approval_type",
        store=True,
        help="Technical flag indicating quotation discount exceeds the allowable 5% limit.",
    )
    approval_state = fields.Selection(
        [
            ('draft', 'Not Submitted'),
            ('waiting_manager', 'Waiting Manager Approval'),
            ('waiting_director', 'Waiting Director Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string="Approval Status",
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        help="Current stage in the discount approval workflow.",
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string="Approved By",
        readonly=True,
        copy=False,
        tracking=True,
        help="The user who approved the quotation discount.",
    )
    approval_date = fields.Datetime(
        string="Approved On",
        readonly=True,
        copy=False,
        tracking=True,
        help="Timestamp when the quotation discount was approved.",
    )
    approved_discount = fields.Float(
        string="Approved Discount (%)",
        readonly=True,
        copy=False,
        digits=(16, 2),
        help="The governing discount level at the time of approval.",
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
        readonly=True,
        copy=False,
        tracking=True,
        help="Reason provided by the approver when rejecting the quotation.",
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends('order_line.discount', 'order_line.price_unit', 'order_line.product_uom_qty')
    def _compute_discount_details(self):
        for order in self:
            standard_lines = order.order_line.filtered(lambda line: not line.display_type)
            if not standard_lines:
                order.max_discount = 0.0
                order.total_discount_amount = 0.0
                order.effective_discount_rate = 0.0
                order.highest_discount = 0.0
                continue

            discounts = [line.discount for line in standard_lines if line.discount > 0.0]
            max_disc = max(discounts) if discounts else 0.0

            total_gross = sum(line.price_unit * line.product_uom_qty for line in standard_lines)
            total_disc_amt = sum(
                (line.price_unit * line.product_uom_qty) * (line.discount / 100.0)
                for line in standard_lines
                if line.discount > 0.0
            )

            effective_rate = (total_disc_amt / total_gross * 100.0) if total_gross > 0.0 else 0.0
            governing = max(max_disc, effective_rate)

            order.max_discount = max_disc
            order.total_discount_amount = total_disc_amt
            order.effective_discount_rate = effective_rate
            order.highest_discount = governing

    @api.depends('highest_discount')
    def _compute_approval_type(self):
        for order in self:
            disc = order.highest_discount
            if disc > 10.0:
                order.approval_type = 'director'
                order.requires_approval = True
            elif disc > 5.0:
                order.approval_type = 'manager'
                order.requires_approval = True
            else:
                order.approval_type = 'none'
                order.requires_approval = False

    # -------------------------------------------------------------------------
    # CRUD OVERRIDES
    # -------------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        # If lines or discounts changed after approval, check if re-approval is required
        if 'order_line' in vals and not self.env.context.get('skip_approval_reset'):
            for order in self:
                if order.state in ('draft', 'sent') and order.approval_state == 'approved':
                    if order.requires_approval and order.highest_discount > (order.approved_discount or 5.0):
                        order.with_context(skip_approval_reset=True).write({
                            'approval_state': 'draft',
                            'approved_by_id': False,
                            'approval_date': False,
                        })
                        order.message_post(
                            body=_(
                                "Discount was modified after approval (new governing discount: %.2f%%). "
                                "Previous approval has been reset and quotation must be resubmitted.",
                            ) % order.highest_discount,
                        )
        return res

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    @api.onchange('global_discount')
    def _onchange_global_discount(self):
        if self.global_discount >= 0.0:
            for line in self.order_line.filtered(lambda item: not item.display_type):
                line.discount = self.global_discount

    def action_apply_global_discount(self):
        """Apply the global_discount percentage to all standard quotation lines."""
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_("You can only apply discounts on draft quotations."))
            standard_lines = order.order_line.filtered(lambda item: not item.display_type)
            if not standard_lines:
                raise UserError(_("Please add at least one product line before applying an overall discount."))
            standard_lines.write({'discount': order.global_discount})

    def action_submit_approval(self):
        """Submit the quotation for approval based on discount threshold and trigger notifications."""
        for order in self:
            if order.state not in ('draft', 'sent'):
                raise UserError(_("Only draft quotations can be submitted for approval."))

            if not order.requires_approval:
                order.approval_state = 'approved'
                order.approved_discount = order.highest_discount
                order.message_post(
                    body=_("Quotation discount (%.2f%%) is within allowable limit (<= 5%%). No approval required.")
                    % order.highest_discount,
                )
                continue

            if order.approval_type == 'director':
                order.approval_state = 'waiting_director'
                order.message_post(
                    body=_(
                        "Quotation submitted for <b>Sales Director Approval</b>.<br/>"
                        "Governing Discount: <b>%.2f%%</b> (Threshold: &gt; 10%%).",
                    ) % order.highest_discount,
                )
            elif order.approval_type == 'manager':
                order.approval_state = 'waiting_manager'
                order.message_post(
                    body=_(
                        "Quotation submitted for <b>Sales Manager Approval</b>.<br/>"
                        "Governing Discount: <b>%.2f%%</b> (Threshold: 5%% - 10%%).",
                    ) % order.highest_discount,
                )

            # Trigger email and activity notification to approvers
            order._send_approval_request_notification()

    def _send_approval_request_notification(self):
        """Send email and schedule activity to approvers (Manager / Director)."""
        template = self.env.ref(
            'sales_approval_commission.email_template_discount_approval_request',
            raise_if_not_found=False,
        )
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)

        for order in self:
            if order.approval_type == 'director':
                group = self.env.ref('sales_approval_commission.group_sale_director', raise_if_not_found=False)
                role_label = _("Sales Director")
            else:
                group = self.env.ref('sales_team.group_sale_manager', raise_if_not_found=False)
                role_label = _("Sales Manager")

            approvers = (
                group.all_user_ids or group.user_ids
            ).filtered(lambda u: u.active and not u.share) if group else self.env['res.users']
            # Target approvers: if multiple exist, prioritize independent approvers
            target_approvers = approvers.filtered(lambda u, current_uid=order.user_id.id: u.id != current_uid) or approvers

            for approver in target_approvers:
                # 1. Schedule Odoo Activity
                if activity_type:
                    try:
                        order.activity_schedule(
                            activity_type_id=activity_type.id,
                            summary=_("Discount Approval Required: %.2f%%") % order.highest_discount,
                            note=_(
                                "Quotation %s for customer %s has a discount of %.2f%% requiring %s approval.",
                            ) % (order.name, order.partner_id.name, order.highest_discount, role_label),
                            user_id=approver.id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        _logger.debug("Failed to schedule activity: %s", exc)

                # 2. Trigger Email to Approver
                if template and approver.email:
                    try:
                        curr_sym = order.currency_id.symbol or ''
                        simple_body = (
                            f'<div style="font-family: sans-serif; font-size: 13px; line-height: 1.5;">'
                            f'<p>Hello,</p>'
                            f'<p>Quotation <strong>{order.name}</strong> requires <strong>{role_label} Approval</strong> before it can be confirmed.</p>'
                            f'<ul>'
                            f'<li><strong>Customer:</strong> {order.partner_id.name or ""}</li>'
                            f'<li><strong>Salesperson:</strong> {order.user_id.name or ""}</li>'
                            f'<li><strong>Governing Discount:</strong> {order.highest_discount:.2f}%</li>'
                            f'<li><strong>Total Discount Amount:</strong> {curr_sym} {order.total_discount_amount:,.2f}</li>'
                            f'<li><strong>Quotation Total:</strong> {curr_sym} {order.amount_total:,.2f}</li>'
                            f'</ul>'
                            f'<p style="margin-top: 15px;">'
                            f'<a href="/web#id={order.id}&amp;model=sale.order&amp;view_type=form" style="font-weight: bold; text-decoration: underline;">'
                            f'Click here to Review &amp; Approve Quotation {order.name}'
                            f'</a></p>'
                            f'</div>'
                        )
                        template.send_mail(
                            order.id,
                            email_values={
                                'email_to': approver.email_formatted or approver.email,
                                'body_html': simple_body,
                            },
                            force_send=True,
                        )
                    except Exception as err:  # noqa: BLE001
                        _logger.debug("Immediate email delivery deferred: %s", err)
                        order.message_post(
                            body=_(
                                "Approval notification email queued for <b>%s</b> (%s).",
                            ) % (approver.name, approver.email),
                        )

    def action_approve(self):
        """Approve the quotation discount. Enforces role checks and anti-self-approval rule."""
        for order in self:
            is_director = self.env.user.has_group('sales_approval_commission.group_sale_director')

            # Prevent self-approval on salesperson quotations
            # Sales Director has executive authority to approve quotations
            if order.user_id and order.user_id == self.env.user and not is_director:
                raise UserError(_(
                    "You cannot approve your own quotation as a salesperson. "
                    "An independent Sales Manager or Sales Director must review and approve it.",
                ))

            # Role validation
            if order.approval_state == 'waiting_director':
                if not is_director:
                    raise UserError(_(
                        "This quotation requires Sales Director approval because the discount (%.2f%%) exceeds 10%%. "
                        "You do not have the required Sales Director permissions.",
                    ) % order.highest_discount)
            elif order.approval_state == 'waiting_manager':
                if not (self.env.user.has_group('sales_team.group_sale_manager') or is_director):
                    raise UserError(_(
                        "This quotation requires Sales Manager approval because the discount (%.2f%%) is between 5%% and 10%%. "
                        "You do not have the required Sales Manager permissions.",
                    ) % order.highest_discount)
            elif order.approval_state in ('draft', 'rejected'):
                # Direct approval by authorized user
                if order.approval_type == 'director' and not is_director:
                    raise UserError(_("Only a Sales Director can approve this quotation."))
                if order.approval_type == 'manager' and not (self.env.user.has_group('sales_team.group_sale_manager') or is_director):
                    raise UserError(_("Only a Sales Manager or Director can approve this quotation."))

            order.write({
                'approval_state': 'approved',
                'approved_by_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
                'approved_discount': order.highest_discount,
                'rejection_reason': False,
            })
            order.message_post(
                body=_(
                    "Quotation discount (%.2f%%) was approved by <b>%s</b>.",
                ) % (order.highest_discount, self.env.user.name),
            )

    def action_reject_dialog(self):
        """Open rejection wizard to record approver feedback."""
        self.ensure_one()
        is_director = self.env.user.has_group('sales_approval_commission.group_sale_director')
        if self.user_id and self.user_id == self.env.user and not is_director:
            raise UserError(_("You cannot review or reject your own quotation."))

        return {
            'name': _("Reject Quotation Discount"),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            },
        }

    def action_reset_to_draft_approval(self):
        """Reset rejected or pending quotation back to draft approval status."""
        for order in self:
            order.write({
                'approval_state': 'draft',
                'approved_by_id': False,
                'approval_date': False,
            })
            order.message_post(body=_("Quotation approval state reset to Draft."))

    # -------------------------------------------------------------------------
    # CONFIRMATION RESTRICTION OVERRIDE
    # -------------------------------------------------------------------------
    def action_confirm(self):
        """Validate discount approvals before confirming the quotation."""
        for order in self:
            if order.requires_approval and order.approval_state != 'approved':
                if order.approval_state == 'waiting_manager':
                    raise UserError(_(
                        "Quotation '%s' cannot be confirmed. It is currently awaiting Sales Manager approval "
                        "(Governing discount: %.2f%%).",
                    ) % (order.name, order.highest_discount))
                if order.approval_state == 'waiting_director':
                    raise UserError(_(
                        "Quotation '%s' cannot be confirmed. It is currently awaiting Sales Director approval "
                        "(Governing discount: %.2f%%).",
                    ) % (order.name, order.highest_discount))
                if order.approval_state == 'rejected':
                    raise UserError(_(
                        "Quotation '%s' was rejected and cannot be confirmed.\nRejection Reason: %s",
                    ) % (order.name, order.rejection_reason or _('No reason specified')))
                req = "Sales Director" if order.highest_discount > 10.0 else "Sales Manager"
                raise UserError(_(
                    "Quotation '%s' has a discount of %.2f%% and requires %s approval before it can be confirmed. "
                    "Please click 'Submit for Approval'.",
                ) % (order.name, order.highest_discount, req))

        return super().action_confirm()
