package hostmetrics

import (
	"bufio"
	"os"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

// Facts describes the host itself — what changes rarely, as opposed to Snapshot which is a
// moving sample. R70: sent with every heartbeat so the job page can show "where did this run"
// (OS, kernel, CPUs, memory and disk size, how long the box has been up) without a separate
// inventory step. Hostname and IPs are deliberately only what the server already knows from
// enrollment; no network interfaces are read.
type Facts struct {
	OS          string  `json:"os,omitempty"`     // PRETTY_NAME from /etc/os-release
	Kernel      string  `json:"kernel,omitempty"` // /proc/sys/kernel/osrelease
	Arch        string  `json:"arch,omitempty"`   // runtime.GOARCH
	CPUs        int     `json:"cpus,omitempty"`   // runtime.NumCPU
	MemTotalMB  uint64  `json:"mem_total_mb,omitempty"`
	DiskTotalGB float64 `json:"disk_total_gb,omitempty"` // of the mount passed to Collect
	UptimeS     int64   `json:"uptime_s,omitempty"`
	Load5       float64 `json:"load5,omitempty"`
	Load15      float64 `json:"load15,omitempty"`
	Timezone    string  `json:"timezone,omitempty"` // the agent's local zone, so cron times can be read
	Virt        string  `json:"virt,omitempty"`     // container|vm|"" — from /proc/1/cgroup / dmi, best effort
}

func osRelease() string {
	f, err := os.Open("/etc/os-release")
	if err != nil {
		return ""
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if v, ok := strings.CutPrefix(sc.Text(), "PRETTY_NAME="); ok {
			return strings.Trim(v, `"`)
		}
	}
	return ""
}

func readTrim(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

func virt() string {
	if b, err := os.ReadFile("/proc/1/cgroup"); err == nil {
		s := string(b)
		if strings.Contains(s, "docker") || strings.Contains(s, "kubepods") || strings.Contains(s, "containerd") {
			return "container"
		}
	}
	if _, err := os.Stat("/.dockerenv"); err == nil {
		return "container"
	}
	if v := strings.ToLower(readTrim("/sys/class/dmi/id/sys_vendor")); v != "" {
		for _, k := range []string{"qemu", "kvm", "vmware", "xen", "amazon", "google", "microsoft", "digitalocean", "virtualbox"} {
			if strings.Contains(v, k) {
				return "vm"
			}
		}
	}
	return ""
}

// CollectFacts is cheap (a handful of small reads) and safe to call on every heartbeat.
func CollectFacts(mount string) Facts {
	f := Facts{OS: osRelease(), Kernel: readTrim("/proc/sys/kernel/osrelease"), Arch: runtime.GOARCH, CPUs: runtime.NumCPU(), Virt: virt()}
	if mt, _ := meminfo(); mt > 0 {
		f.MemTotalMB = mt / 1024
	}
	var st syscall.Statfs_t
	if err := syscall.Statfs(mount, &st); err == nil && st.Blocks > 0 {
		f.DiskTotalGB = float64(st.Blocks) * float64(st.Bsize) / 1e9
		f.DiskTotalGB = float64(int(f.DiskTotalGB*10)) / 10
	}
	if fs := strings.Fields(readTrim("/proc/uptime")); len(fs) > 0 {
		if up, err := strconv.ParseFloat(fs[0], 64); err == nil {
			f.UptimeS = int64(up)
		}
	}
	if fs := strings.Fields(readTrim("/proc/loadavg")); len(fs) >= 3 {
		f.Load5, _ = strconv.ParseFloat(fs[1], 64)
		f.Load15, _ = strconv.ParseFloat(fs[2], 64)
	}
	if tz := os.Getenv("TZ"); tz != "" {
		f.Timezone = tz
	} else if l, err := os.Readlink("/etc/localtime"); err == nil {
		if i := strings.Index(l, "zoneinfo/"); i >= 0 {
			f.Timezone = l[i+len("zoneinfo/"):]
		}
	}
	return f
}
