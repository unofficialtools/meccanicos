# The fleet VM test's script (tests/fleet.nix prepends EXPECTED_A,
# EXPECTED_B and MECCANICOS).
import shlex

start_all()
hq.wait_for_unit("mos-fleet-setup.service")
hq.wait_for_unit("sshd.service")
admin.wait_for_unit("multi-user.target")
ws1.wait_for_unit("multi-user.target")


def a(cmd, ok=True, timeout=900):
    """A command as the admin mrossi, in the fleet repository."""
    c = "su - mrossi -c " + shlex.quote("cd ~/fleet 2>/dev/null; " + cmd + " 2>&1")
    return admin.succeed(c, timeout=timeout) if ok else admin.fail(c, timeout=timeout)


def a_until(cmd, timeout=300):
    admin.wait_until_succeeds("su - mrossi -c " + shlex.quote("cd ~/fleet; " + cmd), timeout=timeout)


SSH_WS = ("ssh -F /dev/null -i /etc/ssh/ssh_host_ed25519_key -o IdentitiesOnly=yes "
          "-o UserKnownHostsFile=/etc/mos-fleet/known_hosts -o HostKeyAlias=mos-fleet-server "
          "-o BatchMode=yes fleet@hq")


def password_is(pw):
    return ("perl -e 'my $h=(getpwnam(\"lbianchi\"))[1]; "
            f"exit(defined $h && crypt(\"{pw}\", $h) eq $h ? 0 : 1)'")


def passwd_as_lbianchi(old, new):
    lines = shlex.quote(f"{old}\n{new}\n{new}\n")
    return f"su lbianchi -s /bin/sh -c {shlex.quote(f'printf %s {lines} | mos-passwd --stdin')} 2>&1"


with subtest("server init"):
    fp = hq.succeed("ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub").split()[1]
    hq.succeed("mos-fleet server admin-key /etc/test-keys/mrossi.pub")
    print(hq.succeed("mos-fleet server status"))

with subtest("a wrong fingerprint stops init"):
    out = a("mos-fleet init --server hq --fingerprint SHA256:wrongwrongwrong --organization X "
            "--admin mrossi --full-name M --dir /tmp/nope", ok=False)
    assert "not SHA256:wrong" in out, out

with subtest("init: the repository, pushed"):
    print(a(f"mos-fleet init --server hq --fingerprint {fp} --organization 'Example Corp' --admin mrossi "
            f"--full-name 'Mario Rossi' --meccanicos path:{MECCANICOS} --flake /etc/test-fleet/flake.nix",
            timeout=1800))

with subtest("a profile and a person"):
    a("mos-fleet profile add office")
    a("mos-fleet person add lbianchi 'Laura Bianchi' --group office")
    print(a("mos-fleet validate", timeout=1800))
    print(a("mos-fleet push --no-eval"))

with subtest("the server refuses what isn't valid"):
    out = a("sed -i 's/^uid = 2001/uid = 2000/' people/lbianchi.toml && git commit -qam 'same uid' "
            "&& git push origin main", ok=False)
    assert "push refused" in out and "uid 2000" in out, out
    a("git reset -q --hard origin/main")
    out = a("git commit -q --amend -m rewritten && git push -f origin main", ok=False)
    assert "can't be rewritten" in out, out
    a("git reset -q --hard origin/main")
    out = a("git push ssh://fleet@hq/etc/passwd main", ok=False)
    assert "fleet.git" in out, out

with subtest("prepare ws1, install it (as mos-install does)"):
    print(a("mos-fleet host prepare ws1 --profile office --unlock tpm-pin --to /tmp/stick"))
    b = "/tmp/stick/meccanicos/fleet/ws1"
    key = admin.succeed(f"cat {b}/enroll.key")
    recipient = admin.succeed(f"cat {b}/admins.txt").split()[0]
    assert "server_host_key" in admin.succeed(f"cat {b}/corporate.config")
    ws1.succeed("install -d -m 700 /var/lib/mos-fleet")
    ws1.succeed(f"printf %s {shlex.quote(key)} > /var/lib/mos-fleet/enroll.key && chmod 600 /var/lib/mos-fleet/enroll.key"
                " && cp /var/lib/mos-fleet/enroll.key /root/enroll.key")
    ws1.succeed(f"echo test-recovery-key | age -a -r {recipient} > /var/lib/mos-fleet/recovery.age")
    ws1.succeed("systemctl restart mos-fleet-agent")
    a_until("mos-fleet host pending | grep 'mos-fleet host add'", timeout=180)
    ws1.wait_until_succeeds("journalctl -u mos-fleet-agent | grep -q \"doesn't know this computer yet\"", timeout=120)
    ws1.succeed("test ! -e /var/lib/mos-fleet/enroll.key")
    out = ws1.fail("ssh -F /dev/null -i /root/enroll.key -o IdentitiesOnly=yes -o BatchMode=yes "
                   "-o UserKnownHostsFile=/etc/mos-fleet/known_hosts -o HostKeyAlias=mos-fleet-server "
                   "fleet@hq enroll < /dev/null 2>&1")
    assert "Permission denied" in out, out

with subtest("add ws1: it switches to the system the server built"):
    out = a("mos-fleet host add ws1 --yes --push")
    ws_fp = ws1.succeed("ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub").split()[1]
    assert ws_fp in out, out
    ws1.wait_until_succeeds(f"test $(readlink -f /run/current-system) = {EXPECTED_A}", timeout=900)
    ws1.succeed("id lbianchi | grep -q office", "id mrossi | grep -q wheel")
    a_until("mos-fleet status ws1 | grep 'up to date'", timeout=120)
    print(a("mos-fleet status"))

with subtest("passwords"):
    a("echo First-pass-1 | mos-fleet password set lbianchi --stdin")
    ws1.wait_until_succeeds(password_is("First-pass-1"), timeout=60)
    out = ws1.fail(passwd_as_lbianchi("wrong", "Second-pass-2"))
    assert "wrong" in out, out
    print(ws1.succeed(passwd_as_lbianchi("First-pass-1", "Second-pass-2")))
    ws1.succeed(password_is("Second-pass-2"))
    for _ in range(5):
        ws1.fail(passwd_as_lbianchi("wrong", "Third-pass-3"))
    out = ws1.fail(passwd_as_lbianchi("Second-pass-2", "Third-pass-3"))
    assert "too many" in out, out
    out = ws1.fail("printf 'x\\nAnother-pass-4\\nAnother-pass-4\\n' | mos-passwd --stdin 2>&1")
    assert "only people" in out, out

with subtest("jobs, shell, logs"):
    out = a("mos-fleet run --host ws1 -- uname -n")
    assert "ws1" in out, out
    out = a("mos-fleet shell ws1 -- hostname", timeout=120)
    assert "ws1" in out, out
    ws1.succeed("logger -p user.warning fleet-test-log-line")
    a_until("mos-fleet logs ws1 | grep fleet-test-log-line", timeout=180)

with subtest("the TUI's data: every tab and pane, from the server"):
    out = a("mos-fleet tui --check")
    for x in ("== Computers", "== ws1 › Logs", "== ws1 › Builds", "== ws1 › Deployments", "== ws1 › Jobs",
              "== People", "== Groups", "== Profiles", "== Changes", "== Audit", "mrossi", "office"):
        assert x in out, (x, out)
    a("mos-fleet tui --demo --check")

with subtest("what a computer's key may not do"):
    out = ws1.fail(f"{SSH_WS} status 2>&1")
    assert "unknown request" in out, out
    out = ws1.fail(f"echo '{{\"system\": \"{EXPECTED_B}\"}}' | {SSH_WS} fetch 2>&1")
    assert "not the system" in out, out
    out = ws1.fail(f"{SSH_WS.replace(' fleet@hq', ' -W 127.0.0.1:22 fleet@hq')} 2>&1")
    assert "prohibited" in out, out
    out = ws1.fail("ssh-keygen -q -t ed25519 -N '' -f /root/other && ssh -F /dev/null -i /root/other "
                   "-o IdentitiesOnly=yes -o BatchMode=yes -o UserKnownHostsFile=/etc/mos-fleet/known_hosts "
                   "-o HostKeyAlias=mos-fleet-server fleet@hq status 2>&1")
    assert "Permission denied" in out, out

with subtest("an update reaches ws1"):
    # As the TUI does it: change the files, commit them later, together.
    a("mos-fleet person add gverdi 'Giulia Verdi' --no-commit")
    a("mos-fleet member add office gverdi --no-commit")
    out = a("mos-fleet diff --worktree")
    assert "gverdi may log in" in out, out
    out = a("mos-fleet push --no-eval", ok=False)
    assert "not committed" in out, out
    a("mos-fleet commit -m 'Giulia joins the office'")
    assert "Giulia joins" in a("git log -1 --format=%s")
    print(a("mos-fleet diff"))
    a("mos-fleet push --no-eval")
    ws1.wait_until_succeeds(f"test $(readlink -f /run/current-system) = {EXPECTED_B}", timeout=900)
    ws1.succeed("id gverdi")
    ws1.succeed(password_is("Second-pass-2"))

with subtest("recovery key, audit, backup"):
    out = a("mos-fleet recover ws1")
    assert "test-recovery-key" in out, out
    out = a("mos-fleet audit")
    assert "password-changed" in out and "enrolled" in out and "push" in out, out
    hq.succeed("mos-fleet server backup /root/backup")
    hq.succeed("test -s /root/backup/state.db -a -s /root/backup/secrets.db -a -s /root/backup/fleet.bundle")

with subtest("restore the server from its backup: ws1 comes back"):
    jobs_before = a("mos-fleet jobs ws1")
    print(hq.succeed("mos-fleet server restore /root/backup --yes 2>&1"))
    hq.succeed("ls -d /var/lib/mos-fleet.before-restore-*/fleet.git")
    hq.succeed("test $(stat -c %U:%a /var/lib/mos-fleet/state.db) = fleet:600")
    a_until("mos-fleet status ws1 | grep -q 'online.*up to date'", timeout=300)
    out = a("mos-fleet run --host ws1 -- uname -n")
    assert "ws1" in out, out
    out = a("mos-fleet jobs ws1")
    assert out.count("exit 0") == jobs_before.count("exit 0") + 1, (jobs_before, out)

with subtest("retire ws1"):  # (also: the restored repository takes pushes)
    # Retired while its agent isn't connected (as after a switch, or off):
    # it learns from the refused key, not from the server's goodbye.
    ws1.systemctl("stop mos-fleet-agent")
    t = ws1.succeed("date +%s").strip()
    a("mos-fleet host retire ws1 --push")
    a_until("mos-fleet status --all | grep 'ws1.*retired'", timeout=60)
    ws1.systemctl("start mos-fleet-agent")
    ws1.wait_until_succeeds(f"journalctl -u mos-fleet-agent --since @{t} | grep -q 'no longer in the fleet'", timeout=120)
    out = ws1.fail(f"{SSH_WS} session < /dev/null 2>&1")
    assert "Permission denied" in out, out
