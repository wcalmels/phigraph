# Licensing Strategy

## Current state

The 4.0.0 source package currently carries the MIT license inherited from the private development baseline. MIT permits reuse, modification, resale and proprietary hosted forks with minimal obligations.

## Recommended public-release model

Before making the repository public, obtain legal review of a dual-license model:

1. **Community license: AGPL-3.0.** Modified versions made available to users over a network must provide corresponding source under the license.
2. **Commercial license.** Customers may purchase terms permitting closed-source embedding, OEM distribution, private modifications, enterprise warranties, support and negotiated obligations.

This preserves an open community path while protecting the hosted-service and OEM business model more effectively than MIT.

## Alternative

A source-available license such as BSL 1.1 can restrict competitive production use before a future change date, but it is not an OSI open-source license. This may reduce adoption and should only be selected after legal and commercial review.

## Decision gate

Do not change the repository visibility to public until all of the following are approved:

- ownership and contributor rights;
- community license;
- commercial license agreement;
- trademark policy for TUCH and PhiGraph;
- third-party dependency compatibility;
- treatment of Cyber datasets and validation artifacts.

This document is a product recommendation, not legal advice.
