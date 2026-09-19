self:
{
  name = "leave-burndown";

  nodes.machine =
    { pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];
      services.leave-burndown = {
        enable = true;
        secretKeyFile = "/etc/leave-burndown-key";
      };
      environment.etc."leave-burndown-key".text = "test-secret-key";
    };

  testScript = ''
    machine.wait_for_unit("leave-burndown.service")
    machine.wait_for_open_port(5050)

    # Renders the page, chart and static files.
    machine.succeed("curl -sf http://127.0.0.1:5050/ | grep -q '<svg class=\"chart chart-wide\"'")
    machine.succeed("curl -sf http://127.0.0.1:5050/static/style.css")

    # The secret key credential reaches the app's environment.
    machine.succeed(
        "tr '\\0' '\\n' < /proc/$(systemctl show -p MainPID --value leave-burndown.service)/environ"
        " | grep -qx 'SECRET_KEY=test-secret-key'"
    )

    # Writes land in the state directory as the dynamic user.
    machine.succeed(
        "curl -sf -o /dev/null -d 'label=Test&start=2026-10-05&end=2026-10-09&status=booked' http://127.0.0.1:5050/add"
    )
    machine.succeed("grep -q '\"label\": \"Test\"' /var/lib/private/leave-burndown/leave_data.json")

    # Flexing a bank holiday adds a day of leave and is persisted.
    machine.succeed("curl -sf -o /dev/null -X POST http://127.0.0.1:5050/flex/2027-03-26")
    machine.succeed("grep -q 2027-03-26 /var/lib/private/leave-burndown/leave_data.json")
    machine.succeed("curl -sf http://127.0.0.1:5050/ | grep -q '<b>1</b> flexed'")

    # Data survives a restart, and debug mode is off.
    machine.systemctl("restart leave-burndown.service")
    machine.wait_for_open_port(5050)
    machine.succeed("curl -sf http://127.0.0.1:5050/ | grep -q Test")
    machine.fail("curl -sf http://127.0.0.1:5050/console")
  '';
}
