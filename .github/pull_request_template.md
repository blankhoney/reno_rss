## Summary

<!-- What does this PR do? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Docs / config only

## Test plan

- [ ] `uv run --isolated --with-editable . --extra dev python -m pytest tests -q` passes in changed Python app(s)
- [ ] `uv run --isolated --with-editable . --extra dev ruff check .` returns no errors in changed Python app(s)
- [ ] `npm test` and `npm run build` pass for reader-web changes
- [ ] `docker compose -f infra/compose/docker-compose.base.yml config` succeeds
- [ ] Tested on staging before prod deploy

## Security checklist (for infra changes)

- [ ] No secrets hardcoded or committed
- [ ] `.env` / secret files excluded from diff
- [ ] CODEOWNERS paths require review

## Rollback plan

<!-- If this needs to be reverted, how? e.g. bash infra/scripts/rollback.sh prod <prev-tag> -->
