package hostmetrics

import "testing"

func TestCollectFacts(t *testing.T) {
	f := CollectFacts("/")
	if f.Arch == "" || f.CPUs < 1 {
		t.Fatalf("arch/cpus missing: %+v", f)
	}
	if f.MemTotalMB == 0 || f.DiskTotalGB == 0 || f.UptimeS == 0 {
		t.Fatalf("linux facts missing: %+v", f)
	}
}
