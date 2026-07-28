# Public Repository Checklist

## Mandatory before changing visibility

- [ ] Confirm repository owner and organization (`wcalmels/phigraph` or TUCH organization).
- [ ] Complete secret scan and review Git history.
- [ ] Remove production data, databases, backups and private reports.
- [ ] Decide and legally review the final license.
- [ ] Approve trademark and naming policy.
- [ ] Confirm all bundled datasets may be redistributed.
- [ ] Run the complete test matrix.
- [ ] Build and install the wheel in a clean environment.
- [ ] Build the Docker image.
- [ ] Review all GitHub Actions permissions.
- [ ] Configure branch protection on `main`.
- [ ] Require pull requests and passing CI.
- [ ] Enable Dependabot and CodeQL.
- [ ] Configure private vulnerability reporting.
- [ ] Create release `v4.0.0` from the verified commit only.

## Recommended first visibility

Keep the repository private during local testing and the first VPS staging deployment. Make a selected Community edition public only after the licensing and artifact review is complete.
