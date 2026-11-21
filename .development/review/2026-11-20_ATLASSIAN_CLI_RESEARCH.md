# Atlassian CLI comparison

DeepSeek V4.1 Flash HIGH reviewed all six public sources on 2026-11-20. This is a
documentation comparison, not installation or live compatibility testing. The decisions
that affect AtlaWire are tracked in [TODO.md](../../TODO.md).

| Source | Documented audience | Useful idea for AtlaWire |
| --- | --- | --- |
| [Appfire Bitbucket CLI](https://marketplace.atlassian.com/apps/1211193/bitbucket-command-line-interface-cli) | Server/Data Center; commercial app plus CLI | Command discovery and traceable bulk actions. Avoid requiring a server plugin. |
| [ainoya/atlassian-cli](https://github.com/ainoya/atlassian-cli) | Read-only Jira and Confluence; Cloud and documented partial Data Center support | Explicit deployment and context-path settings. Linked-content expansion is useful later, with strict request budgets. |
| [putcho01/atlassian-cli](https://mcpservers.org/servers/putcho01/atlassian-cli) ([upstream](https://github.com/putcho01/atlassian-cli)) | Jira and Confluence CLI/MCP; Cloud and Data Center PAT support claimed | Group commands by capability and convert Confluence storage to readable Markdown. The directory listing is not independent proof. |
| [open-cli-collective/atlassian-cli](https://github.com/open-cli-collective/atlassian-cli) | Cloud Jira and Confluence | Stable error categories and a compact agent output mode. Do not remove AtlaWire's existing JSON shapes. |
| [omar16100/atlassian-cli](https://github.com/omar16100/atlassian-cli) | Cloud-oriented suite | Preview before executing writes, and a controlled raw API escape hatch. Cloud fixtures are not proof of older Server/Data Center behavior. |
| [avivsinai/bitbucket-cli](https://github.com/avivsinai/bitbucket-cli) | Cloud and Data Center Bitbucket | Pin a command to its configured context, bound requests and output, and keep headless credentials tied to the destination. Adopt the ideas in the CLI before considering MCP. |

## Priorities

1. Finish `bbk` workflow parity before adding a new interface. Verify a product's actual
   endpoints and authentication on the intended editions rather than copying a Cloud profile.
2. Make result limits, completeness, and diagnostic categories consistent so automated callers
   can act on them. Keep product projections small but retain explicit raw output where useful.
3. Design instance-bound credentials and preview/apply writes before bulk operations. Do not
   infer write safety from a successful command or automatically replay an ambiguous write.

The review did not find one documented tool covering the same three self-hosted products
with those workflow and safety requirements. It did not establish that no such tool exists.
