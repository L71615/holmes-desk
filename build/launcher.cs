using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

// 源码模式下的启动器：编译成带图标的 exe，快捷方式指向它，
// 由它去拉起 python -m holmes_desk，并把子进程的输出写进日志。
// 双击失败时不再"静默无反应"：非零退出会把 traceback 直接弹出来。
class HolmesDeskLauncher
{
    static string logPath;
    static readonly object gate = new object();
    static readonly StringBuilder stderrBuf = new StringBuilder();

    [STAThread]
    static void Main()
    {
        string dir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
        logPath = Path.Combine(dir, "holmesdesk-launcher.log");

        try
        {
            string py = FindPythonW();
            Log("launch  dir=" + dir + "  python=" + py);

            ProcessStartInfo psi = new ProcessStartInfo(py, "-m holmes_desk");
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.StandardOutputEncoding = Encoding.UTF8;
            psi.StandardErrorEncoding = Encoding.UTF8;

            string oldPath = Environment.GetEnvironmentVariable("PYTHONPATH");
            psi.EnvironmentVariables["PYTHONPATH"] = string.IsNullOrEmpty(oldPath) ? dir : dir + ";" + oldPath;
            psi.EnvironmentVariables["PYTHONUTF8"] = "1";
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            Process p = new Process();
            p.StartInfo = psi;
            p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e)
            {
                if (e.Data != null) Log("  out| " + e.Data);
            };
            p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e)
            {
                if (e.Data == null) return;
                Log("  err| " + e.Data);
                lock (gate) { if (stderrBuf.Length < 4000) stderrBuf.AppendLine(e.Data); }
            };

            p.Start();
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            Log("started pid=" + p.Id);

            // 等子进程结束（窗口关闭时退出）。这段期间启动器是隐藏的，不占用户注意力。
            p.WaitForExit();
            Log("exited  code=" + p.ExitCode);

            if (p.ExitCode != 0)
            {
                string detail;
                lock (gate) { detail = stderrBuf.ToString().Trim(); }
                if (detail.Length > 1500) detail = detail.Substring(detail.Length - 1500);
                MessageBox.Show(
                    "HolmesDesk 启动失败（退出码 " + p.ExitCode + "）。\n\n"
                        + (detail.Length > 0 ? detail : "没有输出，详见日志。")
                        + "\n\n日志：" + logPath,
                    "HolmesDesk",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
        catch (Exception ex)
        {
            Log("ERROR " + ex);
            MessageBox.Show(
                "启动失败：" + ex.Message + "\n\n详见 " + logPath,
                "HolmesDesk",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    static void Log(string line)
    {
        try
        {
            lock (gate)
            {
                File.AppendAllText(logPath, DateTime.Now.ToString("HH:mm:ss") + "  " + line + "\r\n", Encoding.UTF8);
            }
        }
        catch { }
    }

    static string FindPythonW()
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates = new string[]
        {
            Path.Combine(local, @"Programs\Python\Python313\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python312\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python311\pythonw.exe"),
            Path.Combine(local, @"Programs\Python\Python310\pythonw.exe"),
            @"C:\Python313\pythonw.exe",
            @"C:\Python312\pythonw.exe",
            @"C:\Python311\pythonw.exe",
            @"C:\Python310\pythonw.exe"
        };
        foreach (string c in candidates)
        {
            if (File.Exists(c)) return c;
        }
        return "pythonw.exe";
    }
}
