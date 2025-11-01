from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from secrets import randbelow
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db, login_manager


DEFAULT_NOTIFICATION_PREFERENCES = {
    "signup": True,
    "login": True,
    "workspace_invite": True,
    "plan_updates": True,
    "workspace_updates": True,
    "new_entries": True,
    "general_updates": True,
}


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Organization(TimestampMixin, db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id"))
    stripe_customer_id = db.Column(db.String(120))
    trial_ends_at = db.Column(db.DateTime)

    users = db.relationship("User", backref="organization", lazy=True)
    offices = db.relationship("Office", backref="organization", lazy=True)
    workspaces = db.relationship("Workspace", backref="organization", lazy=True)
    carriers = db.relationship("Carrier", backref="organization", lazy=True)
    producers = db.relationship("Producer", backref="organization", lazy=True)
    customers = db.relationship("Customer", backref="organization", lazy=True)
    policies = db.relationship("Policy", backref="organization", lazy=True)
    rule_sets = db.relationship("CommissionRuleSet", backref="organization", lazy=True)
    import_batches = db.relationship("ImportBatch", backref="organization", lazy=True)
    commission_transactions = db.relationship("CommissionTransaction", backref="organization", lazy=True)
    payout_statements = db.relationship("PayoutStatement", backref="organization", lazy=True)
    categories = db.relationship("CategoryTag", backref="organization", lazy=True)
    subscriptions = db.relationship("Subscription", backref="organization", lazy=True)


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    tier = db.Column(db.Integer, nullable=False, default=0)
    price_per_user = db.Column(db.Numeric(10, 2), nullable=False)
    included_users = db.Column(db.Integer)
    extra_user_price = db.Column(db.Numeric(10, 2))
    max_users = db.Column(db.Integer, nullable=False)
    max_carriers = db.Column(db.Integer, nullable=False)
    max_rows_per_month = db.Column(db.Integer, nullable=False)
    includes_quickbooks = db.Column(db.Boolean, default=False)
    includes_producer_portal = db.Column(db.Boolean, default=False)
    includes_api = db.Column(db.Boolean, default=False)

    organizations = db.relationship("Organization", backref="plan", lazy=True)


class Office(TimestampMixin, db.Model):
    __tablename__ = "offices"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    timezone = db.Column(db.String(64))

    workspaces = db.relationship("Workspace", backref="office", lazy=True)
    memberships = db.relationship(
        "OfficeMembership",
        backref="office",
        lazy=True,
        cascade="all, delete-orphan",
    )


class Workspace(TimestampMixin, db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True)
    name = db.Column(db.String(120), nullable=False)

    agent = db.relationship(
        "User",
        backref=db.backref("managed_workspace", uselist=False),
        foreign_keys=[agent_id],
    )
    memberships = db.relationship(
        "WorkspaceMembership",
        backref="workspace",
        lazy=True,
        cascade="all, delete-orphan",
    )


class OfficeMembership(TimestampMixin, db.Model):
    __tablename__ = "office_memberships"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(32))


class WorkspaceMembership(TimestampMixin, db.Model):
    __tablename__ = "workspace_memberships"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    workspace_id = db.Column(
        db.Integer, db.ForeignKey("workspaces.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(32))


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="producer")
    status = db.Column(db.String(32), nullable=False, default="active")
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    last_login = db.Column(db.DateTime)
    notification_preferences = db.Column(
        db.JSON, default=lambda: dict(DEFAULT_NOTIFICATION_PREFERENCES)
    )
    two_factor_enabled = db.Column(db.Boolean, nullable=False, default=True)
    two_factor_secret = db.Column(db.String(255))
    two_factor_expires_at = db.Column(db.DateTime)

    producer = db.relationship(
        "Producer",
        backref="user",
        uselist=False,
        foreign_keys="Producer.user_id",
    )
    workspace_memberships = db.relationship(
        "WorkspaceMembership",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    office_memberships = db.relationship(
        "OfficeMembership",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )


    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def display_name_for_ui(self) -> str:
        if getattr(self, "producer", None) and self.producer and self.producer.display_name:
            return self.producer.display_name
        return self.email

    def wants_notification(self, category: str) -> bool:
        prefs = self.notification_preferences or {}
        default = DEFAULT_NOTIFICATION_PREFERENCES.get(category, True)
        return bool(prefs.get(category, default))

    def set_notification_preferences(self, categories: list[str]) -> None:
        allowed = set(DEFAULT_NOTIFICATION_PREFERENCES.keys())
        selected = {key: (key in categories) for key in allowed}
        self.notification_preferences = selected

    def generate_two_factor_code(self) -> str:
        code = f"{randbelow(1_000_000):06d}"
        self.two_factor_secret = generate_password_hash(code)
        self.two_factor_expires_at = datetime.utcnow() + timedelta(minutes=10)
        return code

    def verify_two_factor_code(self, candidate: str | None) -> bool:
        if not candidate or not self.two_factor_secret:
            return False
        if self.two_factor_expires_at and self.two_factor_expires_at < datetime.utcnow():
            return False
        return check_password_hash(self.two_factor_secret, candidate.strip())

    def clear_two_factor_challenge(self) -> None:
        self.two_factor_secret = None
        self.two_factor_expires_at = None

    def record_workspace_membership(self, workspace: "Workspace", role: str | None = None) -> None:
        if not workspace:
            return
        existing = next(
            (
                membership
                for membership in self.workspace_memberships
                if membership.workspace_id == workspace.id
            ),
            None,
        )
        if existing:
            if role and existing.role != role:
                existing.role = role
            return
        membership = WorkspaceMembership(
            org_id=self.org_id,
            workspace_id=workspace.id,
            user_id=self.id,
            role=role,
        )
        self.workspace_memberships.append(membership)
        if workspace.office:
            self.record_office_membership(workspace.office)

    def record_office_membership(self, office: "Office") -> None:
        if not office:
            return
        existing = next(
            (
                membership
                for membership in self.office_memberships
                if membership.office_id == office.id
            ),
            None,
        )
        if existing:
            return
        membership = OfficeMembership(
            org_id=self.org_id,
            office_id=office.id,
            user_id=self.id,
        )
        self.office_memberships.append(membership)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Carrier(TimestampMixin, db.Model):
    __tablename__ = "carriers"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    download_type = db.Column(db.String(32), nullable=False, default="csv")
    default_ruleset_id = db.Column(db.Integer, db.ForeignKey("commission_rulesets.id"))

    ruleset = db.relationship("CommissionRuleSet", backref="default_for_carriers", foreign_keys=[default_ruleset_id])
    mappings = db.relationship("Mapping", backref="carrier", lazy=True)
    policies = db.relationship("Policy", backref="carrier", lazy=True)
    batches = db.relationship("ImportBatch", backref="carrier", lazy=True)


class Producer(TimestampMixin, db.Model):
    __tablename__ = "producers"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    display_name = db.Column(db.String(120), nullable=False)
    default_split = db.Column(db.Numeric(5, 2), nullable=False, default=100)

    commissions = db.relationship("CommissionTransaction", backref="producer", lazy=True)
    payout_statements = db.relationship("PayoutStatement", backref="producer", lazy=True)

    workspace = db.relationship("Workspace", backref="producers")

    agent = db.relationship(
        "User",
        backref="managed_producers",
        foreign_keys=[agent_id],
    )


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    external_ids = db.Column(db.JSON)
    emails = db.Column(db.JSON)
    phones = db.Column(db.JSON)

    policies = db.relationship("Policy", backref="customer", lazy=True)


class Policy(TimestampMixin, db.Model):
    __tablename__ = "policies"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    carrier_id = db.Column(db.Integer, db.ForeignKey("carriers.id"))
    policy_number = db.Column(db.String(120), nullable=False)
    lob = db.Column(db.String(80))
    effective = db.Column(db.Date)
    expiration = db.Column(db.Date)
    status = db.Column(db.String(32), default="active")
    writing_agent_id = db.Column(db.Integer, db.ForeignKey("producers.id"))

    writing_agent = db.relationship("Producer", backref="policies", foreign_keys=[writing_agent_id])
    commission_transactions = db.relationship("CommissionTransaction", backref="policy", lazy=True)


class CommissionRuleSet(TimestampMixin, db.Model):
    __tablename__ = "commission_rulesets"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    effective_from = db.Column(db.Date, default=datetime.utcnow)

    rules = db.relationship("CommissionRule", backref="ruleset", lazy=True, cascade="all, delete-orphan")


class CommissionRule(TimestampMixin, db.Model):
    __tablename__ = "commission_rules"

    id = db.Column(db.Integer, primary_key=True)
    ruleset_id = db.Column(db.Integer, db.ForeignKey("commission_rulesets.id"), nullable=False)
    match_fields = db.Column(db.JSON, nullable=False, default={})
    basis = db.Column(db.String(32), nullable=False, default="gross_commission")
    rate = db.Column(db.Numeric(5, 2))
    flat_amount = db.Column(db.Numeric(10, 2))
    new_vs_renewal = db.Column(db.String(32), default="any")
    priority = db.Column(db.Integer, default=0)


class ImportBatch(TimestampMixin, db.Model):
    __tablename__ = "import_batches"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    carrier_id = db.Column(db.Integer, db.ForeignKey("carriers.id"))
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    producer_id = db.Column(db.Integer, db.ForeignKey("producers.id"))
    period_month = db.Column(db.String(7), nullable=False)
    source_type = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="uploaded")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    file_path = db.Column(db.String(255))

    rows = db.relationship("ImportRow", backref="batch", lazy=True, cascade="all, delete-orphan")
    creator = db.relationship("User", backref="import_batches", foreign_keys=[created_by])
    workspace = db.relationship("Workspace", backref="import_batches")
    producer = db.relationship("Producer", backref="imports", foreign_keys=[producer_id])


class ImportRow(TimestampMixin, db.Model):
    __tablename__ = "import_rows"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id"), nullable=False)
    raw = db.Column(db.JSON, nullable=False)
    normalized = db.Column(db.JSON)
    row_hash = db.Column(db.String(128))
    match_status = db.Column(db.String(32), default="unmatched")
    policy_id = db.Column(db.Integer, db.ForeignKey("policies.id"))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    confidence = db.Column(db.Numeric(5, 2))

    policy = db.relationship("Policy")
    customer = db.relationship("Customer")


class CommissionTransaction(TimestampMixin, db.Model):
    __tablename__ = "commission_txns"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey("policies.id"))
    producer_id = db.Column(db.Integer, db.ForeignKey("producers.id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("import_batches.id"))
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    txn_date = db.Column(db.Date, nullable=False)
    premium = db.Column(db.Numeric(12, 2))
    commission = db.Column(db.Numeric(12, 2))
    basis = db.Column(db.String(32))
    split_pct = db.Column(db.Numeric(5, 2))
    amount = db.Column(db.Numeric(12, 2))
    category = db.Column(db.String(32), default="unspecified")
    carrier_name = db.Column(db.String(120))
    product_type = db.Column(db.String(64))
    source = db.Column(db.String(16), default="import")
    status = db.Column(db.String(32), default="provisional")
    notes = db.Column(db.Text)
    manual_amount = db.Column(db.Numeric(12, 2))
    manual_split_pct = db.Column(db.Numeric(5, 2))
    override_source = db.Column(db.String(32))
    override_applied_at = db.Column(db.DateTime)
    override_applied_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    batch = db.relationship(
        "ImportBatch", backref="commission_transactions", foreign_keys=[batch_id]
    )
    workspace = db.relationship(
        "Workspace", backref="commission_transactions", foreign_keys=[workspace_id]
    )
    creator = db.relationship(
        "User", backref="commission_transactions_created", foreign_keys=[created_by]
    )
    override_actor = db.relationship(
        "User",
        backref="commission_overrides_applied",
        foreign_keys=[override_applied_by],
    )
    overrides = db.relationship(
        "CommissionOverride",
        backref="transaction",
        lazy=True,
        cascade="all, delete-orphan",
    )


class CommissionOverride(TimestampMixin, db.Model):
    __tablename__ = "commission_overrides"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("commission_txns.id"), nullable=False)
    override_type = db.Column(db.String(16), nullable=False)
    flat_amount = db.Column(db.Numeric(12, 2))
    percent = db.Column(db.Numeric(5, 2))
    split_pct = db.Column(db.Numeric(5, 2))
    applied_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notes = db.Column(db.Text)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    applier = db.relationship(
        "User", backref="commission_overrides", foreign_keys=[applied_by]
    )


class CategoryTag(TimestampMixin, db.Model):
    __tablename__ = "category_tags"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    kind = db.Column(db.String(32), nullable=False, default="line")
    is_default = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("org_id", "name", "kind", name="uq_category_tag"),
    )


class PayoutStatement(TimestampMixin, db.Model):
    __tablename__ = "payout_statements"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    producer_id = db.Column(db.Integer, db.ForeignKey("producers.id"))
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"))
    period = db.Column(db.String(7), nullable=False)
    totals = db.Column(db.JSON)
    pdf_path = db.Column(db.String(255))
    finalized_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    finalized_at = db.Column(db.DateTime)

    finalizer = db.relationship("User", backref="finalized_statements", foreign_keys=[finalized_by])
    workspace = db.relationship("Workspace", backref="payout_statements", foreign_keys=[workspace_id])


class ESAgencyBill(TimestampMixin, db.Model):
    __tablename__ = "es_agencybill"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey("policies.id"))
    invoice_no = db.Column(db.String(120))
    billed = db.Column(db.Numeric(12, 2))
    collected = db.Column(db.Numeric(12, 2))
    commission_due = db.Column(db.Numeric(12, 2))
    paid_on = db.Column(db.Date)


class Mapping(TimestampMixin, db.Model):
    __tablename__ = "mappings"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    carrier_id = db.Column(db.Integer, db.ForeignKey("carriers.id"))
    column_map = db.Column(db.JSON, nullable=False)
    sample_path = db.Column(db.String(255))


class Coupon(TimestampMixin, db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    stripe_coupon_id = db.Column(db.String(120))
    internal_code = db.Column(db.String(80), unique=True)
    applies_to_plan = db.Column(db.String(80))
    expires_at = db.Column(db.DateTime)
    max_redemptions = db.Column(db.Integer)
    trial_extension_days = db.Column(db.Integer, nullable=False, default=0)


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"))
    stripe_sub_id = db.Column(db.String(120))
    plan = db.Column(db.String(80))
    status = db.Column(db.String(32))
    trial_end = db.Column(db.DateTime)


class APIKey(TimestampMixin, db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    token_hash = db.Column(db.String(128), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    scopes = db.Column(db.JSON, default=list)
    token_prefix = db.Column(db.String(16))
    token_last4 = db.Column(db.String(4))
    revoked_at = db.Column(db.DateTime)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @property
    def masked_token(self) -> str:
        if self.token_last4:
            return f"•••• {self.token_last4}"
        return "Not available"


class AuditLog(TimestampMixin, db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(120), nullable=False)
    entity = db.Column(db.String(120))
    entity_id = db.Column(db.Integer)
    before = db.Column(db.JSON)
    after = db.Column(db.JSON)
    ts = db.Column(db.DateTime, default=datetime.utcnow)


class WorkspaceNote(TimestampMixin, db.Model):
    __tablename__ = "workspace_notes"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    office_id = db.Column(db.Integer, db.ForeignKey("offices.id"))
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"))
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    scope = db.Column(db.String(16), nullable=False, default="personal")
    title = db.Column(db.String(120))
    content = db.Column(db.Text, default="")

    workspace = db.relationship("Workspace", backref="notes", foreign_keys=[workspace_id])
    office = db.relationship("Office", backref="notes", foreign_keys=[office_id])
    owner = db.relationship("User", backref="notes", foreign_keys=[owner_id])


class WorkspaceChatMessage(TimestampMixin, db.Model):
    __tablename__ = "workspace_chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)

    workspace = db.relationship("Workspace", backref="chat_messages", foreign_keys=[workspace_id])
    author = db.relationship("User", backref="chat_messages", foreign_keys=[author_id])
