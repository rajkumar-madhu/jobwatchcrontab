# Team, invitations and multi-factor sign-in

Add people, give them the right role, and require a second factor for password sign-in. Everything
here is under **Settings → Team** and **Settings → Sign-in security**, and in the
[API](/docs/api/team).

## Invite people (admins)
1. Enter the person's email and choose a role, then **Send invite**.
2. Copy the link that appears and send it to them. **It is shown once**: JobWatch stores only a hash.
3. They open the link, create an account (or sign in) **with that email address**, and join with the
   role you chose.

An invitation works once, expires after seven days and only joins the address it was sent to; signing
in with a different email does not join anyone. Revoke a pending invitation from the same list.
Only owners can invite admins.

## Roles
| Role | Can |
| --- | --- |
| Viewer | Read everything |
| Developer, SRE | Create and change jobs, handle incidents |
| DevOps | Alerting, on-call, agents, integrations |
| Admin | People, API keys, single sign-on, imports |
| Owner | Sign-in policy, SSO enforcement, SCIM, audit streams, deleting the organization |

Admins can change anyone's role up to DevOps and remove members. Only owners can make someone an
admin. Owners cannot be changed or removed here. Members marked **Directory** are provisioned by
[SCIM](scim): their role follows directory groups.

## Require multi-factor sign-in (owners)
Turn on **Require multi-factor sign-in**. Then:

- Members who sign in with a **password** must also enter a code from an authenticator app. The next
  time they sign in, they are asked to set one up.
- Sign-in with **Google or GitHub** is refused for this organization, because JobWatch cannot see
  whether those accounts use a second factor.
- Members who sign in through your **identity provider** get multi-factor authentication from it.
  See [single sign-on](sso).

> [!NOTE]
> This needs the server's Keycloak admin client. When it is not configured, the setting cannot be
> turned on, and a sign-in that cannot be checked is refused, never allowed.

## Password policy
Password accounts need at least 12 characters, not the username or email, and not one of the last
three passwords. Self-hosted: the policy is in the Keycloak realm file.

## Upgrading a self-hosted install
Run the database migration (`0028`) and re-run `deploy/keycloak/import.sh`. It gives the service
account the `view-users` and `manage-users` roles that multi-factor enforcement needs.
