"""
ODW.ai Desk — Customer Resolver

Resolves or creates customers based on channel identifiers.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.models.customer import Customer


class CustomerResolver:
    """
    Customer Resolver.

    Looks up customers by channel-specific identifier (phone, email, session ID)
    and creates new customer records when needed.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_or_create(
        self,
        channel: str,
        identifier: str,
        display_name: str | None = None,
    ) -> Customer:
        """
        Resolve customer by channel identifier or create a new one.

        Args:
            channel: Channel type (whatsapp, webchat, email, etc.)
            identifier: Channel-specific identifier
            display_name: Display name — set on creation and used to fill in a
                missing name on an existing customer (never overwrites)

        Returns:
            Existing or new Customer entity
        """
        # Query using JSONB containment
        result = await self.db.execute(
            select(Customer).where(
                Customer.channel_identifiers[channel].as_string() == identifier
            )
        )
        customer = result.scalar_one_or_none()

        if customer is None:
            customer = Customer(
                channel_identifiers={channel: identifier},
                display_name=display_name,
                metadata_={},
            )
            self.db.add(customer)
            await self.db.flush()
        elif display_name and not (customer.display_name or "").strip():
            # Contact enrichment (Chatwoot-style): adopt the channel profile
            # name (e.g. WhatsApp contact) when the customer has none yet;
            # never overwrite a name an agent has already set.
            customer.display_name = display_name

        return customer

    async def get_customer(self, customer_id: str) -> Customer | None:
        """Get customer by ID."""
        result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        return result.scalar_one_or_none()
