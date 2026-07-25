"""Payment domain — Razorpay/UPI integration, escrow, refunds.

Handles all financial transactions on the platform:
- Marketplace order payments (escrow until delivery)
- Insurance premium payments (direct to insurer)
- Refunds (cancelled orders, rejected claims)

Payment flow:
1. Farmer initiates payment → Platform creates Razorpay order
2. Farmer pays via UPI/card/netbanking → Razorpay processes
3. Razorpay sends webhook → Platform verifies signature
4. Payment held in escrow (marketplace) or released immediately (insurance)
5. On delivery confirmation → escrow released to supplier
6. On cancellation → refund initiated

See KrishiSetu_Architecture_Plan.md §14.7 (marketplace) and §14.6 (insurance)
for payment-related workflow specifications.
"""
