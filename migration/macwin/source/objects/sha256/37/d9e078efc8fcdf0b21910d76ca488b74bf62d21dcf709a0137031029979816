#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${MACWIN_WINE_BUILD_DIR:-$ROOT_DIR/refs/Whisky-wow64-game-build}"

if [ ! -f "$BUILD_DIR/Makefile" ]; then
  echo "Missing Wine build Makefile: $BUILD_DIR" >&2
  exit 1
fi

targets=(
  dlls/dwrite/x86_64-windows/dwrite.dll
  dlls/dwrite/i386-windows/dwrite.dll
  dlls/dwrite/dwrite.so
  dlls/authz/x86_64-windows/authz.dll
  dlls/authz/i386-windows/authz.dll
  dlls/netutils/x86_64-windows/netutils.dll
  dlls/netutils/i386-windows/netutils.dll
  dlls/netapi32/x86_64-windows/netapi32.dll
  dlls/netapi32/i386-windows/netapi32.dll
  dlls/netapi32/netapi32.so
  dlls/wkscli/x86_64-windows/wkscli.dll
  dlls/wkscli/i386-windows/wkscli.dll
  dlls/atlthunk/x86_64-windows/atlthunk.dll
  dlls/atlthunk/i386-windows/atlthunk.dll
  dlls/actxprxy/x86_64-windows/actxprxy.dll
  dlls/actxprxy/i386-windows/actxprxy.dll
  dlls/comctl32_v6/x86_64-windows/comctl32_v6.dll
  dlls/comctl32_v6/i386-windows/comctl32_v6.dll
  dlls/msacm32/x86_64-windows/msacm32.dll
  dlls/msacm32/i386-windows/msacm32.dll
  dlls/winmm/x86_64-windows/winmm.dll
  dlls/winmm/i386-windows/winmm.dll
  dlls/wtsapi32/x86_64-windows/wtsapi32.dll
  dlls/wtsapi32/i386-windows/wtsapi32.dll
  dlls/wer/x86_64-windows/wer.dll
  dlls/wer/i386-windows/wer.dll
  dlls/fontsub/x86_64-windows/fontsub.dll
  dlls/fontsub/i386-windows/fontsub.dll
  dlls/d3d10/x86_64-windows/d3d10.dll
  dlls/d3d10/i386-windows/d3d10.dll
  dlls/d3d10_1/x86_64-windows/d3d10_1.dll
  dlls/d3d10_1/i386-windows/d3d10_1.dll
  dlls/d3d10core/x86_64-windows/d3d10core.dll
  dlls/d3d10core/i386-windows/d3d10core.dll
  dlls/d3d11/x86_64-windows/d3d11.dll
  dlls/d3d11/i386-windows/d3d11.dll
  dlls/d3dcompiler_47/x86_64-windows/d3dcompiler_47.dll
  dlls/d3dcompiler_47/i386-windows/d3dcompiler_47.dll
  dlls/dxgi/x86_64-windows/dxgi.dll
  dlls/dxgi/i386-windows/dxgi.dll
  dlls/dcomp/x86_64-windows/dcomp.dll
  dlls/dcomp/i386-windows/dcomp.dll
  dlls/d2d1/x86_64-windows/d2d1.dll
  dlls/d2d1/i386-windows/d2d1.dll
  dlls/dxva2/x86_64-windows/dxva2.dll
  dlls/dxva2/i386-windows/dxva2.dll
  dlls/evr/x86_64-windows/evr.dll
  dlls/evr/i386-windows/evr.dll
  dlls/mfplay/x86_64-windows/mfplay.dll
  dlls/mfplay/i386-windows/mfplay.dll
  dlls/glu32/x86_64-windows/glu32.dll
  dlls/glu32/i386-windows/glu32.dll
  dlls/oledlg/x86_64-windows/oledlg.dll
  dlls/oledlg/i386-windows/oledlg.dll
  dlls/httpapi/x86_64-windows/httpapi.dll
  dlls/httpapi/i386-windows/httpapi.dll
  dlls/iphlpapi/x86_64-windows/iphlpapi.dll
  dlls/iphlpapi/i386-windows/iphlpapi.dll
  dlls/rasapi32/x86_64-windows/rasapi32.dll
  dlls/rasapi32/i386-windows/rasapi32.dll
  dlls/rstrtmgr/x86_64-windows/rstrtmgr.dll
  dlls/rstrtmgr/i386-windows/rstrtmgr.dll
  dlls/rsaenh/x86_64-windows/rsaenh.dll
  dlls/rsaenh/i386-windows/rsaenh.dll
  dlls/bcryptprimitives/x86_64-windows/bcryptprimitives.dll
  dlls/bcryptprimitives/i386-windows/bcryptprimitives.dll
  dlls/uiautomationcore/x86_64-windows/uiautomationcore.dll
  dlls/uiautomationcore/i386-windows/uiautomationcore.dll
  dlls/oleacc/x86_64-windows/oleacc.dll
  dlls/oleacc/i386-windows/oleacc.dll
  dlls/wevtapi/x86_64-windows/wevtapi.dll
  dlls/wevtapi/i386-windows/wevtapi.dll
  dlls/wevtsvc/x86_64-windows/wevtsvc.dll
  dlls/wevtsvc/i386-windows/wevtsvc.dll
  dlls/qmgr/x86_64-windows/qmgr.dll
  dlls/qmgr/i386-windows/qmgr.dll
  dlls/cryptui/x86_64-windows/cryptui.dll
  dlls/cryptui/i386-windows/cryptui.dll
  dlls/credui/x86_64-windows/credui.dll
  dlls/credui/i386-windows/credui.dll
  dlls/esent/x86_64-windows/esent.dll
  dlls/esent/i386-windows/esent.dll
  dlls/powrprof/x86_64-windows/powrprof.dll
  dlls/powrprof/i386-windows/powrprof.dll
  dlls/concrt140/x86_64-windows/concrt140.dll
  dlls/concrt140/i386-windows/concrt140.dll
  dlls/vcomp/x86_64-windows/vcomp.dll
  dlls/vcomp/i386-windows/vcomp.dll
  dlls/vcomp90/x86_64-windows/vcomp90.dll
  dlls/vcomp90/i386-windows/vcomp90.dll
  dlls/vcomp100/x86_64-windows/vcomp100.dll
  dlls/vcomp100/i386-windows/vcomp100.dll
  dlls/vcomp110/x86_64-windows/vcomp110.dll
  dlls/vcomp110/i386-windows/vcomp110.dll
  dlls/vcomp120/x86_64-windows/vcomp120.dll
  dlls/vcomp120/i386-windows/vcomp120.dll
  dlls/vcomp140/x86_64-windows/vcomp140.dll
  dlls/vcomp140/i386-windows/vcomp140.dll
  dlls/wintab32/x86_64-windows/wintab32.dll
  dlls/wintab32/i386-windows/wintab32.dll
  dlls/wlanapi/x86_64-windows/wlanapi.dll
  dlls/wlanapi/i386-windows/wlanapi.dll
  dlls/wldap32/x86_64-windows/wldap32.dll
  dlls/wldap32/i386-windows/wldap32.dll
  dlls/webservices/x86_64-windows/webservices.dll
  dlls/webservices/i386-windows/webservices.dll
  dlls/taskschd/x86_64-windows/taskschd.dll
  dlls/taskschd/i386-windows/taskschd.dll
  dlls/mstask/x86_64-windows/mstask.dll
  dlls/mstask/i386-windows/mstask.dll
  dlls/msctf/x86_64-windows/msctf.dll
  dlls/msctf/i386-windows/msctf.dll
  dlls/mscms/x86_64-windows/mscms.dll
  dlls/mscms/i386-windows/mscms.dll
  dlls/schedsvc/x86_64-windows/schedsvc.dll
  dlls/schedsvc/i386-windows/schedsvc.dll
  dlls/kerberos/x86_64-windows/kerberos.dll
  dlls/kerberos/i386-windows/kerberos.dll
  dlls/kerberos/kerberos.so
  dlls/msv1_0/x86_64-windows/msv1_0.dll
  dlls/msv1_0/i386-windows/msv1_0.dll
  dlls/msv1_0/msv1_0.so
  dlls/mf/x86_64-windows/mf.dll
  dlls/mf/i386-windows/mf.dll
  dlls/mfplat/x86_64-windows/mfplat.dll
  dlls/mfplat/i386-windows/mfplat.dll
  dlls/hid/x86_64-windows/hid.dll
  dlls/hid/i386-windows/hid.dll
  dlls/vcruntime140/x86_64-windows/vcruntime140.dll
  dlls/vcruntime140/i386-windows/vcruntime140.dll
  dlls/vcruntime140_1/x86_64-windows/vcruntime140_1.dll
  dlls/msvcp140/x86_64-windows/msvcp140.dll
  dlls/msvcp140/i386-windows/msvcp140.dll
  dlls/msvcp140_1/x86_64-windows/msvcp140_1.dll
  dlls/msvcp140_1/i386-windows/msvcp140_1.dll
  programs/services/x86_64-windows/services.exe
  programs/rpcss/x86_64-windows/rpcss.exe
  programs/svchost/x86_64-windows/svchost.exe
  programs/svchost/i386-windows/svchost.exe
)

echo "Building Wine game/CAD DLL coverage in $BUILD_DIR"
make -C "$BUILD_DIR" -j"${MACWIN_BUILD_JOBS:-8}" "${targets[@]}"

missing=0
for target in "${targets[@]}"; do
  if [ ! -f "$BUILD_DIR/$target" ]; then
    echo "MISSING $target" >&2
    missing=$((missing + 1))
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Missing $missing DLL target(s)." >&2
  exit 2
fi

echo "Built ${#targets[@]} DLL targets."
