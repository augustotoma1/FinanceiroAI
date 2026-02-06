"""Initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-06 12:00:00.000000

Creates all initial database tables for the Financial Automation System:
- clients: Customer/client data with Brazilian tax identification
- contracts: Service contracts with financial terms and signature tracking
- financial_records: Financial transactions for invoices, payments, and receivables
- signatures: Electronic signature tracking for contract workflow
- integration_tokens: OAuth token storage for external services (Conta Azul, etc.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create all initial database tables.

    Tables created:
    1. clients - Customer/client data
    2. integration_tokens - OAuth tokens for external services
    3. contracts - Service contracts linked to clients
    4. financial_records - Financial transactions linked to clients
    5. signatures - Electronic signature tracking linked to contracts
    """

    # Create clients table
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary key'),
        sa.Column('name', sa.String(length=255), nullable=False, comment='Full name or company name'),
        sa.Column('email', sa.String(length=255), nullable=True, comment='Contact email'),
        sa.Column('phone', sa.String(length=20), nullable=True, comment='Contact phone number'),
        sa.Column('cpf_cnpj', sa.String(length=20), nullable=False, comment='Brazilian tax ID - CPF (individual) or CNPJ (company)'),
        sa.Column('address_street', sa.String(length=255), nullable=True, comment='Street address'),
        sa.Column('address_city', sa.String(length=100), nullable=True, comment='City name'),
        sa.Column('address_state', sa.String(length=2), nullable=True, comment='State abbreviation (e.g., SP, RJ)'),
        sa.Column('address_zip', sa.String(length=10), nullable=True, comment='ZIP/postal code (CEP)'),
        sa.Column('conta_azul_id', sa.String(length=100), nullable=True, comment='External ID from Conta Azul platform'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Additional notes or observations'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True, comment='Last synchronization with Conta Azul timestamp'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cpf_cnpj'),
        sa.UniqueConstraint('conta_azul_id')
    )
    op.create_index(op.f('ix_clients_id'), 'clients', ['id'], unique=False)
    op.create_index(op.f('ix_clients_email'), 'clients', ['email'], unique=False)
    op.create_index(op.f('ix_clients_cpf_cnpj'), 'clients', ['cpf_cnpj'], unique=True)
    op.create_index(op.f('ix_clients_conta_azul_id'), 'clients', ['conta_azul_id'], unique=True)

    # Create integration_tokens table
    op.create_table(
        'integration_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary key'),
        sa.Column('service', sa.String(length=50), nullable=False, comment="Service identifier (e.g., 'conta_azul', 'autentique')"),
        sa.Column('access_token', sa.String(length=1000), nullable=False, comment='OAuth 2.0 access token - consider encryption in production'),
        sa.Column('refresh_token', sa.String(length=1000), nullable=True, comment='OAuth 2.0 refresh token for obtaining new access tokens'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment='Token expiration timestamp (UTC) for refresh logic'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Token creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last token update/refresh timestamp'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service')
    )
    op.create_index(op.f('ix_integration_tokens_id'), 'integration_tokens', ['id'], unique=False)
    op.create_index(op.f('ix_integration_tokens_service'), 'integration_tokens', ['service'], unique=True)

    # Create contracts table (depends on clients)
    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary key'),
        sa.Column('client_id', sa.Integer(), nullable=False, comment='Reference to client who owns this contract'),
        sa.Column('contract_number', sa.String(length=50), nullable=False, comment='Unique contract identifier (e.g., CTR-2024-001)'),
        sa.Column('service_description', sa.Text(), nullable=False, comment='Detailed description of services to be provided'),
        sa.Column('contract_value', sa.Numeric(precision=15, scale=2), nullable=False, comment='Total contract value in BRL (Brazilian Real)'),
        sa.Column('payment_terms', sa.Text(), nullable=False, comment='Payment schedule and terms description'),
        sa.Column('start_date', sa.Date(), nullable=False, comment='Contract start date'),
        sa.Column('end_date', sa.Date(), nullable=True, comment='Contract end date (optional for open-ended contracts)'),
        sa.Column('duration_months', sa.Integer(), nullable=True, comment='Contract duration in months (optional)'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='draft', comment='Contract status: draft, pending_signature, signed, active, expired, cancelled'),
        sa.Column('pdf_url', sa.String(length=500), nullable=True, comment='Path or URL to generated contract PDF document'),
        sa.Column('pdf_filename', sa.String(length=255), nullable=True, comment='Original filename of generated PDF'),
        sa.Column('conversation_id', sa.String(length=100), nullable=True, comment='ID of Claude conversation that generated this contract'),
        sa.Column('autentique_document_id', sa.String(length=100), nullable=True, comment='External ID from Autentique platform for signature tracking'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Additional notes or special clauses'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when contract was signed by all parties'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contract_number'),
        sa.UniqueConstraint('autentique_document_id')
    )
    op.create_index(op.f('ix_contracts_id'), 'contracts', ['id'], unique=False)
    op.create_index(op.f('ix_contracts_client_id'), 'contracts', ['client_id'], unique=False)
    op.create_index(op.f('ix_contracts_contract_number'), 'contracts', ['contract_number'], unique=True)
    op.create_index(op.f('ix_contracts_status'), 'contracts', ['status'], unique=False)
    op.create_index(op.f('ix_contracts_conversation_id'), 'contracts', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_contracts_autentique_document_id'), 'contracts', ['autentique_document_id'], unique=True)

    # Create financial_records table (depends on clients)
    op.create_table(
        'financial_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary key'),
        sa.Column('client_id', sa.Integer(), nullable=False, comment='Reference to client associated with this transaction'),
        sa.Column('transaction_type', sa.String(length=50), nullable=False, comment='Type of transaction: invoice, payment, receivable, expense'),
        sa.Column('transaction_number', sa.String(length=100), nullable=False, comment='Unique transaction identifier (e.g., INV-2024-001)'),
        sa.Column('description', sa.Text(), nullable=False, comment='Description of the transaction'),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False, comment='Transaction amount in BRL (Brazilian Real)'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='BRL', comment='Currency code (default: BRL for Brazilian Real)'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending', comment='Transaction status: pending, paid, overdue, cancelled'),
        sa.Column('transaction_date', sa.Date(), nullable=False, comment='Date when transaction was created/issued'),
        sa.Column('due_date', sa.Date(), nullable=True, comment='Payment due date (for invoices and receivables)'),
        sa.Column('payment_date', sa.Date(), nullable=True, comment='Actual payment date (when status becomes paid)'),
        sa.Column('days_overdue', sa.Integer(), nullable=True, server_default='0', comment='Calculated field - days past due date (0 if not overdue)'),
        sa.Column('conta_azul_id', sa.String(length=100), nullable=True, comment='External ID from Conta Azul platform for sync'),
        sa.Column('payment_method', sa.String(length=50), nullable=True, comment='Payment method: credit_card, bank_transfer, cash, pix, boleto'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Additional notes or observations about the transaction'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True, comment='Last synchronization with Conta Azul timestamp'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_number'),
        sa.UniqueConstraint('conta_azul_id')
    )
    op.create_index(op.f('ix_financial_records_id'), 'financial_records', ['id'], unique=False)
    op.create_index(op.f('ix_financial_records_client_id'), 'financial_records', ['client_id'], unique=False)
    op.create_index(op.f('ix_financial_records_transaction_type'), 'financial_records', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_financial_records_transaction_number'), 'financial_records', ['transaction_number'], unique=True)
    op.create_index(op.f('ix_financial_records_status'), 'financial_records', ['status'], unique=False)
    op.create_index(op.f('ix_financial_records_due_date'), 'financial_records', ['due_date'], unique=False)
    op.create_index(op.f('ix_financial_records_conta_azul_id'), 'financial_records', ['conta_azul_id'], unique=True)

    # Create signatures table (depends on contracts)
    op.create_table(
        'signatures',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary key'),
        sa.Column('contract_id', sa.Integer(), nullable=False, comment='Reference to contract that requires this signature'),
        sa.Column('signer_name', sa.String(length=255), nullable=False, comment='Full name of the person who should sign'),
        sa.Column('signer_email', sa.String(length=255), nullable=False, comment='Email address where signature request is sent'),
        sa.Column('signer_cpf', sa.String(length=20), nullable=True, comment='Brazilian CPF for legal identification (11 digits)'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending', comment='Signature status: pending, signed, declined, expired'),
        sa.Column('autentique_signature_id', sa.String(length=100), nullable=True, comment='External signature ID from Autentique platform (public_id)'),
        sa.Column('signature_token', sa.String(length=255), nullable=True, comment='Unique token for signature link access'),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when signature was completed'),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when signature was declined (if applicable)'),
        sa.Column('ip_address', sa.String(length=45), nullable=True, comment='IP address from which signature was made (supports IPv6)'),
        sa.Column('user_agent', sa.String(length=500), nullable=True, comment='Browser user agent from signature session'),
        sa.Column('signature_method', sa.String(length=50), nullable=True, server_default='email', comment='Method used for signature request: email, sms, etc.'),
        sa.Column('notes', sa.Text(), nullable=True, comment='Additional notes or observations'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('autentique_signature_id')
    )
    op.create_index(op.f('ix_signatures_id'), 'signatures', ['id'], unique=False)
    op.create_index(op.f('ix_signatures_contract_id'), 'signatures', ['contract_id'], unique=False)
    op.create_index(op.f('ix_signatures_signer_email'), 'signatures', ['signer_email'], unique=False)
    op.create_index(op.f('ix_signatures_status'), 'signatures', ['status'], unique=False)
    op.create_index(op.f('ix_signatures_autentique_signature_id'), 'signatures', ['autentique_signature_id'], unique=True)


def downgrade() -> None:
    """
    Drop all tables in reverse order of creation.

    Order is important due to foreign key constraints:
    1. Drop signatures (depends on contracts)
    2. Drop financial_records (depends on clients)
    3. Drop contracts (depends on clients)
    4. Drop integration_tokens (independent)
    5. Drop clients (base table)
    """

    # Drop signatures table
    op.drop_index(op.f('ix_signatures_autentique_signature_id'), table_name='signatures')
    op.drop_index(op.f('ix_signatures_status'), table_name='signatures')
    op.drop_index(op.f('ix_signatures_signer_email'), table_name='signatures')
    op.drop_index(op.f('ix_signatures_contract_id'), table_name='signatures')
    op.drop_index(op.f('ix_signatures_id'), table_name='signatures')
    op.drop_table('signatures')

    # Drop financial_records table
    op.drop_index(op.f('ix_financial_records_conta_azul_id'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_due_date'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_status'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_transaction_number'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_transaction_type'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_client_id'), table_name='financial_records')
    op.drop_index(op.f('ix_financial_records_id'), table_name='financial_records')
    op.drop_table('financial_records')

    # Drop contracts table
    op.drop_index(op.f('ix_contracts_autentique_document_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_conversation_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_status'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_contract_number'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_client_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_id'), table_name='contracts')
    op.drop_table('contracts')

    # Drop integration_tokens table
    op.drop_index(op.f('ix_integration_tokens_service'), table_name='integration_tokens')
    op.drop_index(op.f('ix_integration_tokens_id'), table_name='integration_tokens')
    op.drop_table('integration_tokens')

    # Drop clients table
    op.drop_index(op.f('ix_clients_conta_azul_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_cpf_cnpj'), table_name='clients')
    op.drop_index(op.f('ix_clients_email'), table_name='clients')
    op.drop_index(op.f('ix_clients_id'), table_name='clients')
    op.drop_table('clients')
