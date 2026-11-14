# The welcome email told every tradesman the product was about 3D cladding

The invitation a customer receives is the first thing they read about Concierge. It opened with:

> You draw a house once in a free 3D program, and Concierge measures the outside clad area,
> subtracts the windows and doors, adds your waste, and prices it at your rate per square metre.

and its "first ten minutes" were the cladding workflow — Designs and CAD, rate per m2, `.ifc`
takeoff, "Price this model". A builder, a kitchen fitter or a plumber reading that concludes the
product is not for them. It also signed off as the customer's own business, so it read as if the
tradesman's company had emailed them about an account they had never heard of.

## Fixed

* Opens with what the product is for everyone: a chat window that answers and captures enquiries,
  then quotes, bookings and invoices at **their** rates.
* First steps are generic: Business details → rates → Quotes → put the chat line on the site (or use
  the hosted page/QR).
* Cladding and 3D takeoff are kept, in an explicitly optional section at the end, with the guide link.
* Signed "The Trendi Concierge team / for {business}" instead of impersonating the customer.

## Proof

`tests/test_owner_invite_email.py` (8) now asserts the opening is about the chat window and not
cladding, that the takeoff section still exists, that the sign-off names Trendi Concierge and the
business, and that no price is promised the business has not set. Full suite **1145**.
