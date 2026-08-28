# Amnezia Admin API in XFI_CONNECT

XFI_CONNECT can manage 3X-UI and Amnezia Admin API servers through the same server/key lifecycle.

## Adding an Amnezia server

Use the existing **Admin → Servers → Add server** dialog.

- URL: the Amnezia Admin API base URL, for example `http://127.0.0.1:4001/`
- Authentication: **API key**
- API key: prefix the real key with `amnezia:`

Example:

`amnezia:YOUR_AMNEZIA_ADMIN_API_KEY`

The prefix is local XFI_CONNECT metadata and is stripped before the key is sent to Amnezia. It is never sent as part of the HTTP credential.

## Supported operations

- server health and basic load statistics
- list clients
- create client/profile
- obtain the generated Amnezia configuration
- delete client/profile
- enable/disable state where supported by the Admin API
- expiry extension through the Admin API
- XFI_CONNECT key synchronization and subscription-mode provisioning

Traffic reset and arbitrary traffic-limit updates are deliberately reported as unsupported because they do not have a safe 3X-UI-equivalent operation in the Amnezia Admin API adapter.

## Compatibility

Existing 3X-UI servers are unchanged. The adapter is selected only when the stored panel profile is `amnezia_admin_api` or the API token uses the explicit `amnezia:` prefix.
