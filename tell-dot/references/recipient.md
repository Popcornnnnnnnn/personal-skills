# Recipient configuration

Keep actual Slack workspace, recipient user and direct-message conversation IDs in the local owner profile or `~/.config/personal-skills/settings.json` under `tell_dot`. They are routing information, not authentication secrets, and still do not belong in public examples.

Before sending, verify the connector's workspace and live receiving identity. Finn/Dot is a personal recipient name, not a universally installed service. A generic ChatGPT app or a similarly named Slack user is not an equivalent target.

The optional runner accepts configured `workspace_id`, `recipient_user_id` and `conversation_id`. It uses the normal configured Codex/Slack authorization. A draft or dry-run does not send. Message delivery and completion of downstream filing require different receipts. Keep existing archive conventions and provide enough scoped context for the receiving agent to act only within the human's request.
