# Start Reachwise automatically when the lab PC restarts

How it works: when Windows starts and signs in, two minimised windows open on the taskbar, one for the
server and one for ngrok. If either stops, it restarts by itself. With automatic sign-in turned on (step 4),
this happens after any restart, power cut or Windows Update, with no one touching the PC.

It uses the ngrok you installed from the Microsoft Store and the Python in `backend\.venv`, and finds both
by itself. You don't need to edit `settings.bat`.

## Steps

1. **Copy these files** into `backend\windows`, replacing the old ones.
2. **Close any server or ngrok windows** you still have open (Ctrl + C), so they don't clash.
3. **Install.** Open the Start menu, type `PowerShell`, right-click it, choose **Run as administrator**, then:
   ```powershell
   cd C:\Users\user\Downloads\reachwise\backend\windows
   powershell -ExecutionPolicy Bypass -File .\install_autostart.ps1
   ```
   Answer **y** to "Lock the screen…" and **y** to "Start Reachwise now?".
   Wait 30 seconds, then check:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\status.ps1
   ```
   Both lines should say OK.
4. **Turn on automatic sign-in** so a restart doesn't wait at the login screen:
   1. Settings → Accounts → Sign-in options. Turn **off** "For improved security, only allow Windows Hello sign-in".
   2. Press Win + R, type `netplwiz`, press Enter.
   3. Untick **Users must enter a user name and password to use this computer**, click OK, and type your
      Windows password twice. Windows stores it securely; it isn't saved in any of our files.
5. **Test.** Restart the PC and don't touch it. After about a minute, open the website on your phone and
   sign in.

## Day to day

| What | How |
|---|---|
| Is it running? | `status.ps1`, or look for the two minimised windows on the taskbar |
| What went wrong? | `backend\logs\server.log` and `backend\logs\ngrok.log` |
| After changing code or `.env` | Close the "Reachwise Server" window; it starts again from Task Scheduler at the next sign-in, or run `Start-ScheduledTask "Reachwise Server"` |
| Turn it all off | `uninstall_autostart.ps1` as administrator |

Don't close the two minimised windows. Closing them stops the website until the next restart.

## Also worth doing

In the PC's BIOS, set **Restore on AC power loss** to **Power On**, so the PC turns itself back on after a power cut.
