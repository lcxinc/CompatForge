#!/usr/bin/env bash
set -u

ROOT="${MACWIN_ROOT:-$HOME/Library/Application Support/MacWin}"
DOWNLOADS="$ROOT/Downloads"
MANIFEST="$DOWNLOADS/software-sample-downloads.tsv"
LOG="$DOWNLOADS/software-sample-downloads.log"

mkdir -p "$DOWNLOADS"

download_one() {
  local id="$1"
  local category="$2"
  local file_name="$3"
  local url="$4"
  local notes="$5"
  local dest="$DOWNLOADS/$file_name"
  local tmp="$dest.tmp"

  mkdir -p "$(dirname "$dest")"

  if [ -f "$dest" ] && [ -s "$dest" ]; then
    printf 'READY\t%s\t%s\t%s\n' "$category" "$id" "$file_name" | tee -a "$LOG"
    return 0
  fi

  if [ -f "$tmp" ]; then
    printf 'RESUME\t%s\t%s\t%s\n' "$category" "$id" "$file_name" | tee -a "$LOG"
  fi
  printf 'DOWNLOAD\t%s\t%s\t%s\n' "$category" "$id" "$file_name" | tee -a "$LOG"
  local proxy_args=()
  if [ "${MACWIN_DOWNLOAD_NO_PROXY:-0}" = "1" ]; then
    proxy_args=(--noproxy '*')
  fi
  local attempt
  local max_attempts="${MACWIN_DOWNLOAD_ATTEMPTS:-6}"
  for attempt in $(seq 1 "$max_attempts"); do
    printf 'ATTEMPT\t%s/%s\t%s\t%s\n' "$attempt" "$max_attempts" "$category" "$id" | tee -a "$LOG"
    if curl ${proxy_args+"${proxy_args[@]}"} --http1.1 -C - -L --fail --connect-timeout 30 \
      --speed-limit "${MACWIN_DOWNLOAD_MIN_SPEED:-1024}" --speed-time "${MACWIN_DOWNLOAD_SPEED_TIME:-60}" \
      --max-time "${MACWIN_DOWNLOAD_MAX_TIME:-3600}" \
      --output "$tmp" "$url"; then
      if file -b "$tmp" | grep -qi 'HTML'; then
        rm -f "$tmp"
        printf 'FAILED_HTML\t%s\t%s\t%s\t%s\n' "$category" "$id" "$file_name" "$url" | tee -a "$LOG"
        return 1
      fi
      mv "$tmp" "$dest"
      printf 'OK\t%s\t%s\t%s\t%s\n' "$category" "$id" "$file_name" "$notes" | tee -a "$LOG"
      return 0
    fi
    printf 'RETRY_PENDING\t%s\t%s\t%s\tattempt=%s\n' "$category" "$id" "$file_name" "$attempt" | tee -a "$LOG"
    sleep "${MACWIN_DOWNLOAD_RETRY_DELAY:-2}"
  done

  printf 'FAILED\t%s\t%s\t%s\t%s\n' "$category" "$id" "$file_name" "$url" | tee -a "$LOG"
  return 1
}

should_download() {
  local category="$1"
  local id="$2"
  local notes="$3"

  if [ -n "${MACWIN_DOWNLOAD_ONLY:-}" ]; then
    case ",$MACWIN_DOWNLOAD_ONLY," in
      *",$category,"*|*",$id,"*)
        ;;
      *)
        printf 'SKIP_FILTER\t%s\t%s\n' "$category" "$id" | tee -a "$LOG"
        return 1
        ;;
    esac
  fi

  if [ "${MACWIN_INCLUDE_HUGE_SAMPLES:-0}" != "1" ] && [[ "$notes" == *"[huge]"* ]]; then
    printf 'SKIP_HUGE\t%s\t%s\tset MACWIN_INCLUDE_HUGE_SAMPLES=1 to download\n' "$category" "$id" | tee -a "$LOG"
    return 1
  fi

  return 0
}

cat > "$MANIFEST" <<'EOF'
category	id	file_name	url	notes
browser	opera-online	OperaSetup.exe	https://net.geo.opera.com/opera/stable/windows	Official Opera online installer; tests TLS, updater bootstrap, Chromium UI.
browser	opera-offline-x64	Opera_132.0.5905.73_Setup_x64.exe	https://download3.operacdn.com/pub/opera/desktop/132.0.5905.73/win/Opera_132.0.5905.73_Setup_x64.exe	Official Opera x64 offline package; deterministic Wine deployment when the regional online metadata endpoint is unavailable.
browser	edge-enterprise	MicrosoftEdgeEnterpriseX64.msi	https://go.microsoft.com/fwlink/?LinkID=2093437	Microsoft Edge Stable Enterprise x64 MSI.
browser	chrome-enterprise	GoogleChromeStandaloneEnterprise64.msi	https://dl.google.com/tag/s/dl/chrome/install/googlechromestandaloneenterprise64.msi	Google Chrome Enterprise offline MSI; Chromium GPU, sandbox, TLS and updater-service coverage.
browser	firefox-msi	Firefox_Setup_152.0.1.msi	https://download-installer.cdn.mozilla.net/pub/firefox/releases/152.0.1/win64/zh-CN/Firefox%20Setup%20152.0.1.msi	Mozilla Firefox x64 zh-CN MSI; preferred installer for deterministic browser smoke.
browser	firefox-full	Firefox_Setup_152.0.1.exe	https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=zh-CN	Mozilla Firefox full installer; kept as installer/updater compatibility material.
browser	firefox-esr	Firefox_ESR_Setup.exe	https://download.mozilla.org/?product=firefox-esr-latest-ssl&os=win64&lang=zh-CN	Firefox ESR full installer for stable Gecko/browser regression coverage.
browser	firefox-developer	Firefox_Developer_Edition_Setup.exe	https://download.mozilla.org/?product=firefox-devedition-latest-ssl&os=win64&lang=zh-CN	Firefox Developer Edition full installer; Gecko developer browser with devtools-heavy UI, CJK text and profile coverage.
browser	opera-gx-online	OperaGXSetup.exe	https://net.geo.opera.com/opera_gx/stable/windows	Opera GX official online installer; Chromium-family browser bootstrap, gaming browser UI and updater/TLS coverage.
browser	brave-standalone	BraveBrowserStandaloneSetup.exe	https://github.com/brave/brave-browser/releases/download/v1.91.175/BraveBrowserStandaloneSetup.exe	Brave x64 standalone installer.
browser	brave-standalone-32	BraveBrowserStandaloneSetup32.exe	https://github.com/brave/brave-browser/releases/download/v1.91.175/BraveBrowserStandaloneSetup32.exe	Brave 32-bit standalone installer for WOW64 coverage.
browser	vivaldi-stable	Vivaldi.7.9.3970.47.x64.exe	https://downloads.vivaldi.com/stable/Vivaldi.7.9.3970.47.x64.exe	Official Vivaldi x64 installer; Chromium browser with dense native UI.
browser	librewolf-setup	librewolf-152.0.1-2-windows-x86_64-setup.exe	https://dl.librewolf.net/librewolf/152.0.1-2/librewolf-152.0.1-2-windows-x86_64-setup.exe	LibreWolf Firefox-family installer; Gecko browser without Mozilla updater stack.
browser	librewolf-portable	librewolf-152.0.1-2-windows-x86_64-portable.zip	https://dl.librewolf.net/librewolf/152.0.1-2/librewolf-152.0.1-2-windows-x86_64-portable.zip	LibreWolf portable archive for no-install launch and profile testing.
browser	floorp-browser	floorp-windows-x86_64.installer.exe	https://github.com/Floorp-Projects/Floorp/releases/download/v12.15.2/floorp-windows-x86_64.installer.exe	Floorp Firefox-family browser; additional Gecko UI, profile, font and TLS coverage.
browser	waterfox	Waterfox_Setup_6.6.15.exe	https://cdn.waterfox.com/waterfox/releases/6.6.15/WINNT_x86_64/Waterfox%20Setup%206.6.15.exe	Waterfox Firefox-family browser; Gecko text rendering, profile and TLS coverage.
browser	palemoon-64	palemoon-34.3.0.1.win64.installer.exe	https://www.palemoon.org/download.php?bits=64&mirror=us&type=installer	Pale Moon Goanna browser x64 installer; independent browser engine and legacy Win32 UI coverage.
browser	palemoon-32	palemoon-34.3.0.1.win32.installer.exe	https://www.palemoon.org/download.php?bits=32&mirror=us&type=installer	Pale Moon Goanna browser 32-bit installer; WOW64 browser and legacy plug-in-adjacent coverage.
browser	tor-browser	TorBrowser-Windows-x86_64.exe	https://sourceforge.net/projects/tor-browser.mirror/files/15.0.16/tor-browser-windows-x86_64-portable-15.0.16.exe/download	Tor Browser portable installer from the Tor Project SourceForge mirror; Firefox-family hardened profile, networking and sandbox-adjacent coverage.
browser	qutebrowser	qutebrowser-3.7.0-amd64.exe	https://github.com/qutebrowser/qutebrowser/releases/download/v3.7.0/qutebrowser-3.7.0-amd64.exe	qutebrowser installer; Python and QtWebEngine browser stack coverage.
browser	qutebrowser-portable	qutebrowser-3.7.0-windows-standalone.zip	https://github.com/qutebrowser/qutebrowser/releases/download/v3.7.0/qutebrowser-3.7.0-windows-standalone.zip	qutebrowser standalone ZIP; no-install QtWebEngine launch and profile coverage.
browser	supermium-64	Supermium_144_64_setup_win10_11.exe	https://github.com/win32ss/supermium/releases/download/v144-r4_01/supermium_144_64_setup_win10_11.exe	Supermium Chromium-family browser for Windows 10/11; Chromium UI, sandbox, GPU and updater-independent launch coverage.
browser	supermium-32	Supermium_144_32_setup.exe	https://github.com/win32ss/supermium/releases/download/v144-r4_01/supermium_144_32_setup.exe	Supermium 32-bit Chromium-family browser; WOW64 browser, text rendering and GPU fallback coverage.
browser	seamonkey-zhcn-64	seamonkey-2.53.23.zh-CN.win64.installer.exe	https://archive.seamonkey-project.org/releases/2.53.23/win64/zh-CN/seamonkey-2.53.23.zh-CN.win64.installer.exe	SeaMonkey Chinese x64 internet suite; Gecko browser, mail/news, classic XUL UI and localized text coverage.
browser	seamonkey-zhcn-32	seamonkey-2.53.21.zh-CN.win32.installer.exe	https://archive.seamonkey-project.org/releases/2.53.21/win32/zh-CN/seamonkey-2.53.21.zh-CN.win32.installer.exe	SeaMonkey Chinese 32-bit legacy browser suite; WOW64 Gecko/XUL, installer and localized text coverage.
browser	min-browser	min-1.35.5-setup.exe	https://github.com/minbrowser/min/releases/download/v1.35.5/min-1.35.5-setup.exe	Min Browser Electron installer; minimal Chromium shell, profile, fonts and updater-independent launch coverage.
browser	min-browser-portable	Min-v1.35.5-windows.zip	https://github.com/minbrowser/min/releases/download/v1.35.5/Min-v1.35.5-windows.zip	Min Browser portable ZIP; no-install Electron browser launch and profile coverage.
browser	ungoogled-chromium-x64	ungoogled-chromium_149.0.7827.155-1.1_installer_x64.exe	https://github.com/ungoogled-software/ungoogled-chromium-windows/releases/download/149.0.7827.155-1.1/ungoogled-chromium_149.0.7827.155-1.1_installer_x64.exe	Ungoogled Chromium x64 installer; modern Chromium without Google updater, useful for sandbox, GPU and TLS isolation checks.
browser	ungoogled-chromium-x86	ungoogled-chromium_149.0.7827.155-1.1_installer_x86.exe	https://github.com/ungoogled-software/ungoogled-chromium-windows/releases/download/149.0.7827.155-1.1/ungoogled-chromium_149.0.7827.155-1.1_installer_x86.exe	Ungoogled Chromium x86 installer; WOW64 Chromium coverage for fonts, GPU fallback and network stack behavior.
browser	ungoogled-chromium-portable	ungoogled-chromium_149.0.7827.155-1.1_windows_x64.zip	https://github.com/ungoogled-software/ungoogled-chromium-windows/releases/download/149.0.7827.155-1.1/ungoogled-chromium_149.0.7827.155-1.1_windows_x64.zip	Ungoogled Chromium portable ZIP; no-install Chromium launch/profile coverage.
browser	brave-portable	brave-portable-win64-1.89.132-99.7z	https://github.com/portapps/brave-portable/releases/download/1.89.132-99/brave-portable-win64-1.89.132-99.7z	Brave portable archive; Chromium profile and extension-style UI without machine installer services.
browser	mullvad-browser	mullvad-browser-windows-x86_64-15.0.16.exe	https://github.com/mullvad/mullvad-browser/releases/download/15.0.16/mullvad-browser-windows-x86_64-15.0.16.exe	Mullvad Browser Windows x64 installer; hardened Firefox/Tor-family browser, sandbox-adjacent profile and network UI coverage.
browser	zen-browser	ZenBrowser-1.21.3b-installer.exe	https://github.com/zen-browser/desktop/releases/download/1.21.3b/zen.installer.exe	Zen Browser Firefox-family Windows installer; modern browser chrome, profile, font rendering and TLS coverage.
browser	otter-browser-portable	otter-browser-win64-weekly120.zip	https://sourceforge.net/projects/otter-browser/files/otter-browser-weekly120/otter-browser-win64-weekly120.zip/download	Otter Browser portable ZIP; Qt WebEngine browser shell, menus, profile and no-install launch coverage.
browser	kmeleon-portable	K-MeleonPortable_76.5.5-2024-12-21.paf.exe	https://portableapps.com/redirect/?a=K-MeleonPortable&s=s&p=&d=pa&f=K-MeleonPortable_76.5.5-2024-12-21.paf.exe	K-Meleon Portable; lightweight Win32 browser with Goanna/Gecko-family rendering and legacy UI coverage.
market	npackd-market	Npackd64-1.26.9.zip	https://github.com/npackd/npackd-cpp/releases/download/version_1.26.9/Npackd64-1.26.9.zip	Npackd package manager portable ZIP; third-party software catalog, package list UI, TLS and installer orchestration coverage.
market	portableapps-platform	PortableApps.com_Platform_Setup_30.4.1.paf.exe	https://sourceforge.net/projects/portableapps/files/PortableApps.com%20Platform/PortableApps.com_Platform_Setup_30.4.1.paf.exe/download	PortableApps.com Platform installer; third-party app marketplace, NSIS installer flow and portable app management coverage.
office	wps-office-online	wps_office_inst.exe	https://wdl1.pcfg.cache.wpscdn.com/wpsdl/wpsoffice/onlinesetup/distsrc/601.1042/wpsinst/wps_office_inst.exe	WPS Office official online installer.
office	libreoffice	LibreOffice_26.2.4_Win_x86-64.msi	https://download.documentfoundation.org/libreoffice/stable/26.2.4/win/x86_64/LibreOffice_26.2.4_Win_x86-64.msi	LibreOffice x64 MSI; large office suite for fonts, CJK text, file dialogs and OLE-style integration.
office	libreoffice-help-zhcn	LibreOffice_26.2.4_Win_x86-64_helppack_zh-CN.msi	https://download.documentfoundation.org/libreoffice/stable/26.2.4/win/x86_64/LibreOffice_26.2.4_Win_x86-64_helppack_zh-CN.msi	LibreOffice Chinese help pack; optional MSI coverage for localized resources.
office	onlyoffice	OnlyOfficeDesktopEditors-x64.exe	https://download.onlyoffice.com/install/desktop/editors/windows/distrib/onlyoffice/DesktopEditors_x64.exe	ONLYOFFICE Desktop Editors; Electron/Chromium office UI, document canvas and GPU fallback coverage.
office	openoffice-zhcn-32	Apache_OpenOffice_4.1.16_Win_x86_install_zh-CN.exe	https://sourceforge.net/projects/openofficeorg.mirror/files/4.1.16/binaries/zh-CN/Apache_OpenOffice_4.1.16_Win_x86_install_zh-CN.exe/download	Apache OpenOffice Chinese 32-bit installer; legacy office/WOW64 sample.
office	texstudio	Texstudio-4.9.5-win-qt6-signed.exe	https://github.com/texstudio-org/texstudio/releases/download/4.9.5/texstudio-4.9.5-win-qt6-signed.exe	Qt6 technical writing/editor sample.
office	texlive-installer	install-tl-windows.exe	https://mirror.ctan.org/systems/texlive/tlnet/install-tl-windows.exe	TeX Live Windows network installer; package manager, Perl/Tk-style UI and long-running installer coverage.
office	thunderbird-zhcn	Thunderbird-latest-win64-zhCN.exe	https://download.mozilla.org/?product=thunderbird-latest-ssl&os=win64&lang=zh-CN	Mozilla Thunderbird mail client; Gecko, TLS, profile and file picker coverage.
office	scribus-legacy	Scribus-1.4.8-windows-x64.exe	https://sourceforge.net/projects/scribus/files/scribus/1.4.8/scribus-1.4.8-windows-x64.exe/download	Desktop publishing sample for PDF/prepress, font and Qt UI coverage.
office	freeplane	Freeplane-Setup-1.13.2.exe	https://github.com/freeplane/freeplane/releases/download/release-1.13.2/Freeplane-Setup-1.13.2.exe	Mind-mapping/knowledge-work sample; Java UI, tree widgets, file dialogs and fonts.
office	drawio	draw.io-30.2.4.msi	https://github.com/jgraph/drawio-desktop/releases/download/v30.2.4/draw.io-30.2.4.msi	Diagram editor sample; Electron canvas, fonts, clipboard and file dialogs.
office	joplin	Joplin-Setup-3.6.15.exe	https://github.com/laurent22/joplin/releases/download/v3.6.15/Joplin-Setup-3.6.15.exe	Markdown note app sample; Electron, SQLite profile, TLS sync UI and text rendering.
office	xournalpp	xournalpp-1.3.5-windows-setup-AMD64.exe	https://github.com/xournalpp/xournalpp/releases/download/v1.3.5/xournalpp-1.3.5-windows-setup-AMD64.exe	PDF annotation and handwriting sample; GTK, input, tablet-adjacent events and PDF rendering.
office	pdfsam-basic	pdfsam-basic-6.0.1-windows-x64.msi	https://github.com/torakiki/pdfsam/releases/download/v6.0.1/pdfsam-basic-6.0.1-windows-x64.msi	PDF split/merge office utility; Java runtime UI, file dialogs and MSI coverage.
office	pdfarranger	pdfarranger-1.14.0-windows-installer.msi	https://github.com/pdfarranger/pdfarranger/releases/download/1.14.0/pdfarranger-1.14.0-windows-installer.msi	PDF Arranger Windows MSI; GTK/Python document workflow, thumbnails, drag ordering and file-dialog coverage.
office	pdfarranger-portable	pdfarranger-1.14.0-windows-portable.zip	https://github.com/pdfarranger/pdfarranger/releases/download/1.14.0/pdfarranger-1.14.0-windows-portable.zip	PDF Arranger portable ZIP; no-install office document workflow and GTK/Python runtime coverage.
office	obsidian	Obsidian-1.12.7.exe	https://github.com/obsidianmd/obsidian-releases/releases/download/v1.12.7/Obsidian-1.12.7.exe	Obsidian note workstation; Electron markdown editor, profile storage, canvas, IME and text rendering coverage.
office	standard-notes	standard-notes-3.201.21-win-x64.exe	https://github.com/standardnotes/app/releases/download/%40standardnotes/desktop%403.201.21/standard-notes-3.201.21-win-x64.exe	Standard Notes x64 installer; encrypted notes Electron app, editor/profile storage, TLS sync UI and text rendering coverage.
office	calibre	calibre-64bit-9.9.0.msi	https://github.com/kovidgoyal/calibre/releases/download/v9.9.0/calibre-64bit-9.9.0.msi	Calibre ebook manager; Qt, large library lists, file dialogs, PDF/ebook conversion UI and MSI coverage.
office	sumatrapdf	SumatraPDF-3.6.1-64-install.exe	https://www.sumatrapdfreader.org/dl/rel/3.6.1/SumatraPDF-3.6.1-64-install.exe	Lightweight PDF/ebook viewer; fast Win32 text, menus, printing and file association coverage.
office	zotero-latest	Zotero-Windows-latest.exe	https://www.zotero.org/download/client/dl?channel=release&platform=win32	Research/reference manager sample; XUL/Firefox-family UI, profile storage, PDF reader, plug-in and TLS coverage.
office	freeoffice	FreeOffice2024.msi	https://www.softmaker.net/down/freeoffice2024.msi	SoftMaker FreeOffice suite; commercial-style office UI, MSI install and document editor coverage.
office	softmaker-office-trial	SoftMakerOffice2024-x64.msi	https://www.softmaker.net/down/softmaker-office-2024-64.msi	SoftMaker Office trial; heavyweight office suite, MSI install, fonts and file dialog coverage.
office	pdfxchange-editor	EditorV11.x64.msi	https://downloads.pdf-xchange.com/EditorV11.x64.msi	PDF-XChange Editor x64 MSI; complex PDF editor UI, printer/OCR-adjacent installer and shell integration coverage.
office	marktext	marktext-win-x64-0.19.1-setup.exe	https://github.com/marktext/marktext/releases/download/v0.19.1/marktext-win-x64-0.19.1-setup.exe	MarkText markdown editor; Electron text rendering, menus, profile storage and file dialogs.
office	pdf24-creator	pdf24-creator.exe	https://download.pdf24.org/pdf24-creator.exe	PDF24 Creator; PDF printer/converter-style office utility, shell integration, dialogs and document workflow coverage.
office	typora	typora-setup-x64.exe	https://download.typora.io/windows/typora-setup-x64.exe	Typora markdown editor; Electron-style editor surface, IME, font rendering and file dialog coverage.
office	naps2	NAPS2-8.2.1-win-x64.exe	https://github.com/cyanfish/naps2/releases/download/v8.2.1/naps2-8.2.1-win-x64.exe	NAPS2 scanner/OCR/PDF workflow sample; WIA/TWAIN-adjacent APIs, image list UI and PDF export coverage.
office	cherrytree	CherryTree-1.7.0-win64-setup.exe	https://github.com/giuspen/cherrytree/releases/download/v1.7.0/cherrytree_1.7.0.0_win64_setup.exe	CherryTree hierarchical notes; GTK UI, rich text, tree widgets, SQLite profile and file dialogs.
office	freemind	FreeMind-Windows-Installer-1.0.1-max.exe	https://sourceforge.net/projects/freemind/files/freemind/1.0.1/FreeMind-Windows-Installer-1.0.1-max.exe/download	FreeMind mind-mapping sample; legacy Java/Swing UI, tree/canvas widgets and installer coverage.
office	projectlibre	ProjectLibre-1.9.8.msi	https://sourceforge.net/projects/projectlibre/files/ProjectLibre/1.9.8/ProjectLibre-1.9.8.msi/download	ProjectLibre project management suite; Java/Swing Gantt charts, Office-style workflow and MSI coverage.
office	ganttproject	ganttproject-3.3.3316.exe	https://github.com/bardsoftware/ganttproject/releases/download/ganttproject-3.3.3316/ganttproject-3.3.3316.exe	GanttProject project scheduling app; bundled Java runtime, Gantt/resource UI and installer coverage.
office	lyx	LyX-251-Installer-1-x64.exe	https://lyx.mirror.garr.it/bin/2.5.1/LyX-251-Installer-1-x64.exe	LyX document processor; Qt technical writing UI, TeX integration checks, fonts and file dialogs.
office	focuswriter	FocusWriter-1.9.0-Windows10-x64.exe	https://gottcode.org/focuswriter/download/?os=windows	FocusWriter distraction-free word processor; Qt6 editor, full-screen windowing, spellcheck and text rendering coverage.
office	focuswriter-portable	FocusWriter-1.9.0-Windows10-x64-portable.zip	https://gottcode.org/focuswriter/download/?os=windowsportable	FocusWriter portable ZIP; no-install Qt6 editor launch and profile coverage.
office	zettlr	Zettlr-4.6.0-x64.exe	https://github.com/Zettlr/Zettlr/releases/download/v4.6.0/Zettlr-4.6.0-x64.exe	Zettlr academic markdown editor; Electron, citation workflow, file tree, IME and typography coverage.
office	jabref	JabRef-5.15.msi	https://github.com/JabRef/jabref/releases/download/v5.15/JabRef-5.15.msi	JabRef bibliography manager; Java desktop UI, database tables, file dialogs, web lookup and citation workflow coverage.
office	jabref-portable	JabRef-5.15-portable_windows.zip	https://github.com/JabRef/jabref/releases/download/v5.15/JabRef-5.15-portable_windows.zip	JabRef portable ZIP; no-install Java desktop launch and profile/library path coverage.
office	sigil	Sigil-2.8.0-Windows-x64-Setup.exe	https://github.com/Sigil-Ebook/Sigil/releases/download/2.8.0/Sigil-2.8.0-Windows-x64-Setup.exe	Sigil ebook editor; Qt/WebEngine-style editor, EPUB archive workflow, fonts and file dialogs.
office	qownnotes	QOwnNotes.zip	https://github.com/pbek/QOwnNotes/releases/download/v26.6.7/QOwnNotes.zip	QOwnNotes portable note app; Qt markdown editor, file tree, sync settings and no-install UI coverage.
office	texworks-win7	TeXworks-win7-setup-0.6.11.exe	https://github.com/TeXworks/texworks/releases/download/release-0.6.11/TeXworks-win7-setup-0.6.11-202602100855-git_7951fd8.exe	TeXworks Win7-compatible installer; Qt document editor, PDF preview and legacy Windows target coverage.
office	miktex-basic	basic-miktex-25.12-x64.exe	https://miktex.org/download/win/basic-miktex-x64.exe	MiKTeX basic installer; TeX package manager, console helpers, path/registry behavior and document toolchain coverage.
office	openboard	OpenBoard_Installer_1.7.3.exe	https://github.com/OpenBoard-org/OpenBoard/releases/download/v1.7.3/OpenBoard_Installer_1.7.3.exe	OpenBoard interactive whiteboard; office/education presentation workflow, Qt UI, canvas, pen input and PDF import/export coverage.
office	pandoc	pandoc-3.10-windows-x86_64.msi	https://github.com/jgm/pandoc/releases/download/3.10/pandoc-3.10-windows-x86_64.msi	Pandoc document converter MSI; command-line document workflow, PATH/registry behavior and Unicode file-name coverage.
office	quarto	quarto-1.9.38-win.msi	https://github.com/quarto-dev/quarto-cli/releases/download/v1.9.38/quarto-1.9.38-win.msi	Quarto publishing system MSI; document toolchain, embedded browser previews and R/Python-adjacent workflow coverage.
office	wxmaxima	wxMaxima-26.06.2-win64.exe	https://github.com/wxMaxima-developers/wxmaxima/releases/download/Version-26.06.2/wxMaxima-26.06.2-win64.exe	wxMaxima Windows installer; math worksheet UI, wxWidgets text rendering and plot/file-dialog coverage.
office	maxima-cas	maxima-5.49.0-win64.exe	https://sourceforge.net/projects/maxima/files/Maxima-Windows/5.49.0-Windows/maxima-5.49.0-win64.exe/download	Maxima CAS Windows bundle; symbolic math, wxMaxima, Gnuplot, Tcl/Tk and scientific plotting compatibility sample.
office	gnuplot	gp604-win64-clang.exe	https://sourceforge.net/projects/gnuplot/files/gnuplot/6.0.4/gp604-win64-clang.exe/download	Gnuplot Windows installer; scientific plotting, console helpers, file associations and font/render backend coverage.
office	labplot	labplot-2.12.1-x86_64-setup.exe	https://download.kde.org/stable/labplot/labplot-2.12.1-x86_64-setup.exe	LabPlot data analysis workstation; KDE/Qt charts, spreadsheet-like tables, plotting and file-dialog coverage.
office	smath-studio	SMathStudioDesktop.1_4_0_9654.Setup.msi	https://smath.com/en-US/files/Download/kTH2c/SMathStudioDesktop.1_4_0_9654.Setup.msi	SMath Studio engineering notebook; WYSIWYG math worksheet, units, plug-in manager and .NET-style desktop UI coverage.
office	dia-diagram	dia-setup-0.97.2-2-unsigned.exe	https://sourceforge.net/projects/dia-installer/files/dia-win32-installer/0.97.2/dia-setup-0.97.2-2-unsigned.exe/download	Dia diagram editor; legacy GTK diagramming app for flowcharts, UML-style drawing, fonts and installer compatibility.
industrial	kicad	Kicad-10.0.3-x86_64.exe	https://github.com/KiCad/kicad-source-mirror/releases/download/10.0.3/kicad-10.0.3-x86_64.exe	Large EDA/CAD installer; high-value industrial compatibility sample.
industrial	kicad-current	kicad-10.0.4-x86_64.exe	https://github.com/KiCad/kicad-source-mirror/releases/download/10.0.4/kicad-10.0.4-x86_64.exe	KiCad current x64 installer; latest EDA stack for schematic/PCB editors, Python plug-ins and OpenGL canvas comparison.
industrial	cura	UltiMaker-Cura-5.13.0-win64-X64.msi	https://github.com/Ultimaker/Cura/releases/download/5.13.0/UltiMaker-Cura-5.13.0-win64-X64.msi	3D printing slicer MSI; Qt/OpenGL workload.
industrial	cura-exe	UltiMaker-Cura-5.13.0-win64-X64.exe	https://github.com/Ultimaker/Cura/releases/download/5.13.0/UltiMaker-Cura-5.13.0-win64-X64.exe	3D printing slicer EXE alternate installer; compares MSI and EXE packaging behavior.
industrial	arduino-ide	arduino-ide_2.3.10_Windows_64bit.exe	https://github.com/arduino/arduino-ide/releases/download/2.3.10/arduino-ide_2.3.10_Windows_64bit.exe	Electron developer/embedded IDE sample.
industrial	wix-cli	wix-cli-x64.msi	https://github.com/wixtoolset/wix/releases/download/v7.0.0/wix-cli-x64.msi	MSI toolchain sample; installer/runtime command coverage.
industrial	dbeaver	dbeaver-ce-latest-win32.win32.x86_64.zip	https://dbeaver.io/files/dbeaver-ce-latest-win32.win32.x86_64.zip	Database workstation portable ZIP; Eclipse/SWT UI, Java runtime, TLS drivers and large lists without NSIS installer noise.
industrial	beekeeper-studio	Beekeeper-Studio-Setup-5.8.1.exe	https://github.com/beekeeper-studio/beekeeper-studio/releases/download/v5.8.1/Beekeeper-Studio-Setup-5.8.1.exe	Database GUI sample; Electron app shell, native dialogs, SQLite/profile and webview rendering.
industrial	sqlitebrowser	DB.Browser.for.SQLite-v3.13.1-win64.msi	https://github.com/sqlitebrowser/sqlitebrowser/releases/download/v3.13.1/DB.Browser.for.SQLite-v3.13.1-win64.msi	SQLite desktop database tool; Qt table rendering, file dialogs and MSI coverage.
industrial	heidisql	HeidiSQL_12.19.0.7314_Setup.exe	https://github.com/HeidiSQL/HeidiSQL/releases/download/v12.19/HeidiSQL_12.19.0.7314_Setup.exe	HeidiSQL database client; native database UI, grids, SSH/TLS settings, installer and credential dialogs.
industrial	heidisql-portable	HeidiSQL_12.19_64_Portable.zip	https://github.com/HeidiSQL/HeidiSQL/releases/download/v12.19/HeidiSQL_12.19_64_Portable.zip	HeidiSQL portable ZIP; no-install database GUI launch and configuration storage coverage.
industrial	pgadmin	pgadmin4-9.16-x64.exe	https://ftp.postgresql.org/pub/pgadmin/pgadmin4/v9.16/windows/pgadmin4-9.16-x64.exe	pgAdmin 4 x64 installer; database administration UI, embedded browser/runtime, TLS and service-adjacent behavior.
industrial	mysql-workbench	mysql-workbench-community-8.0.44-winx64.msi	https://cdn.mysql.com/Downloads/MySQLGUITools/mysql-workbench-community-8.0.44-winx64.msi	MySQL Workbench x64 MSI; database modeling, SQL editor, complex grids and OpenGL/schema diagram coverage.
industrial	gitextensions	GitExtensions-x64-7.0.1.86-c119a52.msi	https://github.com/gitextensions/gitextensions/releases/download/v7.0.1/GitExtensions-x64-7.0.1.86-c119a52.msi	.NET/WinForms developer GUI sample; shell integration, git process launching and DPI/text coverage.
industrial	x64dbg	snapshot_2026-05-27_12-11.zip	https://github.com/x64dbg/x64dbg/releases/download/2026.05.27/snapshot_2026-05-27_12-11.zip	Debugger sample; portable Win32 UI, process/debug APIs and WOW64-sensitive behavior.
industrial	mremoteng	mRemoteNG-Installer-1.76.20.24615.msi	https://github.com/mRemoteNG/mRemoteNG/releases/download/v1.76.20/mRemoteNG-Installer-1.76.20.24615.msi	Remote connection manager sample; .NET/WinForms, tree/grid UI, credential dialogs and protocol plug-ins.
industrial	freecad	FreeCAD_1.1.1-Windows-x86_64-py311-installer.exe	https://github.com/FreeCAD/FreeCAD/releases/download/1.1.1/FreeCAD_1.1.1-Windows-x86_64-py311-installer.exe	FreeCAD workbench; Qt, Python runtime and OpenGL/CAD viewport compatibility sample.
industrial	brlcad	BRL-CAD_7.42.2_win64.msi	https://github.com/BRL-CAD/brlcad/releases/download/rel-7-42-2/BRL-CAD_7.42.2_win64.msi	BRL-CAD solid modeling system; CAD/geometry toolchain, MSI installer and legacy engineering UI coverage.
industrial	librecad	LibreCAD-v2.2.1.5-win64-msvc.exe	https://github.com/LibreCAD/LibreCAD/releases/download/v2.2.1.5/LibreCAD-v2.2.1.5-win64-msvc.exe	LibreCAD 2D CAD sample; Qt drawing surface, font rendering and DXF workflow coverage.
industrial	openscad	OpenSCAD-2021.01-x86-64-Installer.exe	https://files.openscad.org/OpenSCAD-2021.01-x86-64-Installer.exe	OpenSCAD parametric CAD; script editor, Qt UI and OpenGL preview coverage.
industrial	gmsh	gmsh-4.14.1-Windows64.zip	https://gmsh.info/bin/Windows/gmsh-4.14.1-Windows64.zip	Gmsh finite-element mesh generator; OpenGL/FLTK-style UI, CAD import dialogs and no-install engineering workload.
industrial	solvespace	SolveSpace-3.2-x64.exe	https://github.com/solvespace/solvespace/releases/download/v3.2/solvespace_x64.exe	Parametric CAD single-exe sample; OpenGL viewport, constraints UI and no-installer launch.
industrial	godot-win64	Godot_v4.7-stable_win64.exe.zip	https://github.com/godotengine/godot/releases/download/4.7-stable/Godot_v4.7-stable_win64.exe.zip	Godot editor x64 ZIP; game-engine editor, Vulkan/OpenGL path, complex docking UI and no-install launch coverage.
industrial	godot-win32	Godot_v4.7-stable_win32.exe.zip	https://github.com/godotengine/godot/releases/download/4.7-stable/Godot_v4.7-stable_win32.exe.zip	Godot editor x86 ZIP; WOW64 game-engine/editor rendering and input coverage.
industrial	bambu-studio	Bambu_Studio_win-v02.07.01.62-20260616174358.exe	https://github.com/bambulab/BambuStudio/releases/download/v02.07.01.62/Bambu_Studio_win-v02.07.01.62-20260616174358.exe	Bambu Studio 3D-print slicer installer; modern slicer UI, OpenGL preview, account/network panels and dense printer settings coverage.
industrial	bambu-studio-portable	Bambu_Studio_win-v02.07.01.62-20260616174358.zip	https://github.com/bambulab/BambuStudio/releases/download/v02.07.01.62/Bambu_Studio_win-v02.07.01.62-20260616174358.zip	Bambu Studio Windows ZIP; no-install slicer launch, OpenGL preview and profile/config path coverage.
industrial	qucs-s	Qucs-S-26.1.1-win64-setup.exe	https://github.com/ra3xdh/qucs_s/releases/download/26.1.1/Qucs-S-26.1.1-win64-setup.exe	Qucs-S circuit simulator installer; schematic editor, SPICE integration, Qt widgets and engineering plot coverage.
industrial	qucs-s-portable	Qucs-S-26.1.1-win64.zip	https://github.com/ra3xdh/qucs_s/releases/download/26.1.1/Qucs-S-26.1.1-win64.zip	Qucs-S circuit simulator portable ZIP; no-install schematic editor, SPICE integration, Qt widgets and engineering plot coverage.
industrial	logisim-evolution	logisim-evolution-4.1.0-amd64.msi	https://github.com/logisim-evolution/logisim-evolution/releases/download/v4.1.0/logisim-evolution-4.1.0-amd64.msi	Logisim Evolution digital logic IDE MSI; Java UI, circuit canvas, simulation toolbar and education/EDA workflow coverage.
industrial	tiled-map-editor	Tiled-1.12.2_Windows-10+_x86_64.msi	https://github.com/mapeditor/tiled/releases/download/v1.12.2/Tiled-1.12.2_Windows-10%2B_x86_64.msi	Tiled map editor MSI; Qt graphics view, tileset/image import, game tooling workflow and file-dialog coverage.
industrial	qelectrotech	Installer_QElectroTech-0.100.0_x86_64-win64.exe	https://github.com/qelectrotech/qelectrotech-source-mirror/releases/download/0.100/Installer_QElectroTech-0.100.0_x86_64-win64%2Bgit8590-1.exe	Electrical CAD sample; Qt widgets, symbol libraries, project tree and file dialogs.
industrial	prusaslicer	PrusaSlicer-2.9.5-setup.exe	https://github.com/prusa3d/PrusaSlicer/releases/download/version_2.9.5/PrusaSlicer-2.9.5-setup.exe	PrusaSlicer 3D-print workflow; OpenGL preview and complex settings UI coverage.
industrial	ltspice	LTspice64.msi	https://ltspice.analog.com/software/LTspice64.msi	Analog Devices LTspice; circuit simulation sample for MSI, schematic UI, plotting and file dialogs.
industrial	wireshark	Wireshark-latest-x64.exe	https://www.wireshark.org/download/win64/Wireshark-latest-x64.exe	Wireshark network analyzer; Qt UI, packet list rendering, service/driver installer and capture warning coverage.
industrial	geogebra	GeoGebra-Windows-Installer.exe	https://download.geogebra.org/package/win-autoupdate	GeoGebra math/geometry workstation; Electron/webview UI, canvas rendering and updater bootstrap sample.
industrial	geogebra-classic5	GeoGebraClassic5-Windows-Installer.exe	https://download.geogebra.org/package/win	GeoGebra Classic 5 math/geometry workstation; non-Electron fallback for Java/Swing geometry UI and WOW64 coverage.
industrial	qcad-legacy	QCad-2.0.5.0-Installer.exe	https://sourceforge.net/projects/qcadbin-win/files/qcadbin-win-2.0.5.0-1_rel-0.3/QCad%202.0.5.0%20Installer.exe/download	Legacy 32-bit CAD sample for WOW64 and old Win32 UI.
industrial	sweethome3d	SweetHome3D-7.5-windows.exe	https://sourceforge.net/projects/sweethome3d/files/SweetHome3D/SweetHome3D-7.5/SweetHome3D-7.5-windows.exe/download	Interior design/CAD-like Java/OpenGL sample.
industrial	meshlab	MeshLab2025.07-windows_x86_64.exe	https://github.com/cnr-isti-vclab/meshlab/releases/download/MeshLab-2025.07/MeshLab2025.07-windows_x86_64.exe	3D mesh processing sample for OpenGL, Qt and large model UI coverage.
industrial	scilab	Scilab-2026.1.0-x64.exe	https://www.scilab.org/download/2026.1.0/scilab-2026.1.0.bin.x64.exe	Scientific computing and Xcos simulation sample for Java/graphics/runtime coverage.
industrial	octave	Octave-11.3.0-w64-installer.exe	https://ftpmirror.gnu.org/octave/windows/octave-11.3.0-w64-installer.exe	GNU Octave scientific computing installer; large Qt/plotting workload.
industrial	qgis-ltr	QGIS-OSGeo4W-3.44.11-1.msi	https://download.qgis.org/downloads/QGIS-OSGeo4W-3.44.11-1.msi	[huge] QGIS LTR GIS workstation MSI; spatial UI, Qt, Python and plugin coverage.
industrial	openmodelica	OpenModelica-v1.26.9-64bit.exe	https://build.openmodelica.org/omc/builds/windows/releases/1.26/9/64bit/OpenModelica-v1.26.9-64bit.exe	[huge] Modelica simulation suite; heavyweight industrial engineering compatibility sample.
industrial	orcaslicer	OrcaSlicer_Windows_Installer_V2.4.0.exe	https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v2.4.0/OrcaSlicer_Windows_Installer_V2.4.0.exe	OrcaSlicer 3D-print workflow; modern slicer UI, OpenGL preview and dense settings compatibility sample.
industrial	lasergrbl	LaserGRBL-install-7.14.1.exe	https://github.com/arkypita/LaserGRBL/releases/download/v7.14.1/install.exe	LaserGRBL CNC controller; serial-port UI, WinForms controls, G-code preview and machine-control dialog coverage.
industrial	cncjs	cncjs-app-1.11.1-windows-x64.exe	https://github.com/cncjs/cncjs/releases/download/v1.11.1/cncjs-app-1.11.1-windows-x64.exe	CNCjs desktop app; Electron CNC controller UI, serial-port settings, websocket runtime and machine-control workflow coverage.
industrial	slic3r-64	Slic3r-1.3.0.64bit.zip	https://github.com/slic3r/Slic3r/releases/download/1.3.0/Slic3r-1.3.0.64bit.zip	Slic3r legacy 64-bit ZIP; Perl/GUI slicer, OpenGL preview and no-install 3D-print workflow coverage.
industrial	slic3r-32	Slic3r-1.3.0.32bit.zip	https://github.com/slic3r/Slic3r/releases/download/1.3.0/Slic3r-1.3.0.32bit.zip	Slic3r legacy 32-bit ZIP; WOW64 slicer UI and OpenGL preview coverage.
industrial	esphome-flasher-x64	ESPHome-Flasher-1.4.0-Windows-x64.exe	https://github.com/esphome/esphome-flasher/releases/download/1.4.0/ESPHome-Flasher-1.4.0-Windows-x64.exe	ESPHome Flasher x64; serial flashing UI, USB/COM-port enumeration and Electron-style runtime checks.
industrial	esphome-flasher-x86	ESPHome-Flasher-1.4.0-Windows-x86.exe	https://github.com/esphome/esphome-flasher/releases/download/1.4.0/ESPHome-Flasher-1.4.0-Windows-x86.exe	ESPHome Flasher x86; WOW64 serial flashing UI and installer-free single executable coverage.
industrial	stellarium	stellarium-26.1-qt6-win64.exe	https://github.com/Stellarium/stellarium/releases/download/v26.1/stellarium-26.1-qt6-win64.exe	Stellarium planetarium; Qt6/OpenGL scientific visualization, sky viewport and full-screen rendering coverage.
industrial	jasp	JASP-0.97.1-Windows-Community.msi	https://github.com/jasp-stats/jasp-desktop/releases/download/v0.97.1/JASP-0.97.1-Windows-Community.msi	[huge] JASP statistics workstation; Qt/webview-style data UI, tables, plots and MSI coverage.
industrial	librepcb	librepcb-installer-2.1.1-windows-x86_64.exe	https://download.librepcb.org/releases/2.1.1/librepcb-installer-2.1.1-windows-x86_64.exe	LibrePCB EDA sample; Qt schematic/PCB editors, library manager, OpenGL-adjacent canvas and file dialogs.
industrial	rstudio	RStudio-2025.09.0-387.exe	https://download1.rstudio.org/electron/windows/RStudio-2025.09.0-387.exe	RStudio desktop IDE; Electron/Qt-adjacent data science UI, terminals, plots and file dialogs.
industrial	r-base	R-4.6.0-win.exe	https://cran.r-project.org/bin/windows/base/R-4.6.0-win.exe	R for Windows base installer; scientific console, package library layout, registry/PATH behavior and plotting-adjacent workflows.
industrial	julia	Julia-1.12.2-win64.exe	https://julialang-s3.julialang.org/bin/winnt/x64/1.12/julia-1.12.2-win64.exe	Julia scientific computing installer; REPL, package manager, console and plotting-adjacent workflows.
industrial	processing	processing-4.5.2-windows-x64.msi	https://github.com/processing/processing4/releases/download/processing-1313-4.5.2/processing-4.5.2-windows-x64.msi	Processing creative coding IDE; Java/Electron-adjacent editor, sketch runner, OpenGL canvas and MSI coverage.
industrial	opencpn	opencpn_5.14.0-0+4418.91f3b67_setup.exe	https://github.com/OpenCPN/OpenCPN/releases/download/Release_5.14.0/opencpn_5.14.0-0%2B4418.91f3b67_setup.exe	OpenCPN marine navigation workstation; OpenGL chart canvas, wxWidgets UI, serial/GPS-adjacent settings and installer coverage.
industrial	openrocket	OpenRocket-24.12-installer-Windows-x86_64.exe	https://github.com/openrocket/openrocket/releases/download/release-24.12/OpenRocket-24.12-installer-Windows-x86_64.exe	OpenRocket engineering simulator; bundled Java UI, plotting, 2D/3D preview and install4j coverage.
industrial	lazarus-win64	lazarus-4.8-fpc-3.2.2-win64.exe	https://sourceforge.net/projects/lazarus/files/Lazarus%20Windows%2064%20bits/Lazarus%204.8/lazarus-4.8-fpc-3.2.2-win64.exe/download	Lazarus IDE x64; Pascal IDE, form designer, compiler toolchain, Win32 controls and large installer coverage.
industrial	lazarus-win32	lazarus-4.8-fpc-3.2.2-win32.exe	https://sourceforge.net/projects/lazarus/files/Lazarus%20Windows%2032%20bits/Lazarus%204.8/lazarus-4.8-fpc-3.2.2-win32.exe/download	Lazarus IDE x86; WOW64 Pascal IDE, form designer and compiler subprocess coverage.
industrial	codeblocks-mingw	codeblocks-20.03mingw-setup.exe	https://downloads.sourceforge.net/project/codeblocks/Binaries/20.03/Windows/codeblocks-20.03mingw-setup.exe	Code::Blocks with MinGW; native C/C++ IDE, compiler subprocesses, debugger settings and wxWidgets UI coverage.
industrial	thonny	thonny-5.0.0-x64.exe	https://github.com/thonny/thonny/releases/download/v5.0.0/thonny-5.0.0-x64.exe	Thonny Python IDE installer; editor, REPL, subprocess, bundled runtime and educational IDE workflow coverage.
industrial	thonny-portable	thonny-5.0.0-windows-portable-x64.zip	https://github.com/thonny/thonny/releases/download/v5.0.0/thonny-5.0.0-windows-portable-x64.zip	Thonny portable ZIP; no-install Python IDE launch and settings/profile coverage.
industrial	dwsim	DWSIM_v905_win64_setup.exe	https://sourceforge.net/projects/dwsim/files/DWSIM/DWSIM%209.0/9.0.5/DWSIM_v905_win64_setup.exe/download	[huge] DWSIM chemical process simulator; .NET, OpenGL, engineering flowsheet UI and scientific plotting coverage.
industrial	openplc-editor	OpenPLC.Editor_4.2.7.exe	https://github.com/Autonomy-Logic/openplc-editor/releases/download/v4.2.7/OpenPLC.Editor_4.2.7.exe	OpenPLC Editor industrial automation IDE; Electron/PLC workflow, code editor, project tree and installer coverage.
industrial	cloudcompare	CloudCompare_v2.13.2_setup_x64.exe	https://www.cloudcompare.org/release/CloudCompare_v2.13.2_setup_x64.exe	[huge] CloudCompare point-cloud/CAD workstation; OpenGL viewport, plugin loading, large data UI and installer coverage.
industrial	cloudcompare-legacy-32	CloudCompare_v2.6.2_setup_x86.exe	https://www.cloudcompare.org/release/CloudCompare_v2.6.2_setup_x86.exe	CloudCompare last 32-bit Windows installer; WOW64 OpenGL, legacy Qt UI and engineering visualization coverage.
industrial	paraview	ParaView-6.1.0-Windows-Python3.12-msvc2017-AMD64.msi	https://www.paraview.org/paraview-downloads/download.php?submit=Download&version=v6.1&type=binary&os=Windows&downloadFile=ParaView-6.1.0-Windows-Python3.12-msvc2017-AMD64.msi	[huge] ParaView scientific visualization workstation; VTK/OpenGL, Python runtime, MSI install and large-data UI coverage.
runtime	mesa3d-msvc	mesa3d-26.1.2-release-msvc.7z	https://github.com/pal1000/mesa-dist-win/releases/download/26.1.2/mesa3d-26.1.2-release-msvc.7z	Mesa3D Windows MSVC runtime; per-app software OpenGL fallback for ParaView and other OpenGL 3.x scientific visualization workloads.
industrial	graphviz	Graphviz-15.0.0-win64.exe	https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/15.0.0/windows_10_cmake_Release_graphviz-install-15.0.0-win64.exe	Graphviz graph visualization toolchain; Win32 installer, font/rendering stack, command tools and GVEdit coverage.
industrial	qgroundcontrol	QGroundControl-installer.exe	https://d176tv9ibo4jno.cloudfront.net/latest/QGroundControl-installer.exe	QGroundControl drone ground station; Qt/OpenGL map/video UI, serial/UDP settings, joystick-adjacent input and hardware workflow coverage.
industrial	mqtt-explorer	MQTT-Explorer-Setup-0.4.0-beta.6.exe	https://github.com/thomasnordquist/MQTT-Explorer/releases/download/v0.4.0-beta.6/MQTT-Explorer-Setup-0.4.0-beta.6.exe	MQTT Explorer IoT protocol client; Electron UI, TLS settings, tree/list rendering and broker connection workflow coverage.
industrial	sqlitestudio	SQLiteStudio-3.4.17-windows-x64-installer.exe	https://github.com/pawelsalawa/sqlitestudio/releases/download/3.4.17/SQLiteStudio-3.4.17-windows-x64-installer.exe	SQLiteStudio database GUI; Qt table rendering, schema browser, SQL editor and installer coverage.
industrial	ghidra	ghidra_11.4.2_PUBLIC_20250826.zip	https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.4.2_build/ghidra_11.4.2_PUBLIC_20250826.zip	[huge] Ghidra reverse-engineering suite; Java UI, large project tree, decompiler view, external toolchain and archive launch coverage.
industrial	cmake	cmake-4.3.3-windows-x86_64.msi	https://github.com/Kitware/CMake/releases/download/v4.3.3/cmake-4.3.3-windows-x86_64.msi	CMake Windows x64 MSI; native build-tool installer, PATH integration and command-line subprocess coverage.
industrial	eclipse-installer	eclipse-inst-jre-win64.exe	https://www.eclipse.org/downloads/download.php?file=/oomph/epp/2026-03/R/eclipse-inst-jre-win64.exe&r=1	Eclipse Installer with bundled JRE; Java/SWT workbench bootstrap, HTTPS mirror selection and IDE provisioning coverage.
industrial	netbeans-ide	Apache-NetBeans-25-bin-windows-x64.exe	https://archive.apache.org/dist/netbeans/netbeans-installers/25/Apache-NetBeans-25-bin-windows-x64.exe	Apache NetBeans Windows x64 installer; Java/Swing IDE, project tree, editor tabs and build-process coverage.
industrial	msys2	msys2-x86_64-latest.exe	https://github.com/msys2/msys2-installer/releases/download/nightly-x86_64/msys2-x86_64-latest.exe	MSYS2 rolling x64 installer; POSIX shell, pacman bootstrap, console subprocesses and developer toolchain coverage.
industrial	python	python-3.14.2-amd64.exe	https://www.python.org/ftp/python/3.14.2/python-3.14.2-amd64.exe	CPython Windows x64 installer; MSI-like bootstrapper, launcher registration, PATH options and console/runtime smoke coverage.
industrial	nodejs	node-v26.3.1-x64.msi	https://nodejs.org/dist/v26.3.1/node-v26.3.1-x64.msi	Node.js Windows x64 MSI; developer runtime install, PATH integration, npm subprocesses and TLS/package-manager coverage.
industrial	temurin-jdk21	OpenJDK21U-jdk_x64_windows_hotspot_21.0.11_10.zip	https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk	Temurin JDK 21 x64 ZIP; Java runtime/toolchain baseline for Swing, JavaFX-adjacent apps and no-install archive launch coverage.
industrial	saga-gis	saga-9.9.1_x64_setup.exe	https://sourceforge.net/projects/saga-gis/files/SAGA%20-%209/SAGA%20-%209.9.1/saga-9.9.1_x64_setup.exe/download	SAGA GIS workstation; geospatial analysis UI, map rendering, grid/vector workflows and installer coverage.
industrial	osgeo4w	osgeo4w-setup.exe	https://download.osgeo.org/osgeo4w/v2/osgeo4w-setup.exe	OSGeo4W network installer; GIS package manager, setup UI, TLS/download flow and GRASS/QGIS dependency bootstrap coverage.
industrial	orange-data-mining	Orange3-3.40.0-x86_64.exe	https://download.biolab.si/download/files/Orange3-3.40.0-x86_64.exe	[huge] Orange Data Mining standalone installer; Python/Qt visual workflow UI, charts, tables and ML widget coverage.
industrial	epanet-water	epanet2.2_setup.exe	https://github.com/USEPA/EPANET2.2/releases/download/2.2.0/epanet2.2_setup.exe	EPA EPANET water distribution modeling GUI; civil engineering workflow, Delphi/Win32 UI and simulation-file coverage.
industrial	swmm-hydrology	swmm524x64_setup.exe	https://epa.gov/system/files/other-files/2023-08/swmm524%28x64%29_setup.exe	EPA SWMM 5.2.4 x64 installer; stormwater/hydrology modeling UI, map/profile plots and legacy engineering workflow coverage.
industrial	opendss-power	OpenDSSInstaller_1100_1.exe	https://sourceforge.net/projects/electricdss/files/OpenDSS/OpenDSSInstaller_1100_1.exe/download	OpenDSS electric distribution simulator; power-system engineering tools, COM/console components and Win32 installer coverage.
industrial	qmodmaster-64	qModMaster-Win64-exe-0.5.3-beta.zip	https://sourceforge.net/projects/qmodmaster/files/qModMaster-Win64-exe-0.5.3-beta.zip/download	QModMaster 64-bit portable ZIP; Modbus RTU/TCP industrial protocol GUI, serial settings and Qt widget coverage.
industrial	qmodmaster-32	qModMaster-Win32-exe-0.5.2-3.zip	https://sourceforge.net/projects/qmodmaster/files/qModMaster-Win32-exe-0.5.2-3.zip/download	QModMaster 32-bit portable ZIP; WOW64 Modbus RTU/TCP GUI and serial-port dialog coverage.
industrial	mremoteng-1782-x64	mRemoteNG-20260222-v1.78.2-NB-3405-x64.rar	https://github.com/mRemoteNG/mRemoteNG/releases/download/20260222-v1.78.2-NB-%283405%29/mRemoteNG-20260222-v1.78.2-NB-3405-x64.rar	mRemoteNG 1.78.2 NB x64 portable RAR; modern .NET desktop runtime sample that avoids the 1.76.x Wine-Mono native crash.
industrial	dotnet-runtime-10-x64	dotnet-runtime-10.0.9-win-x64.zip	https://builds.dotnet.microsoft.com/dotnet/Runtime/10.0.9/dotnet-runtime-10.0.9-win-x64.zip	.NET Runtime 10.0.9 win-x64 ZIP; hostfxr/CoreCLR runtime payload used by modern .NET apphost samples such as mRemoteNG 1.78.2.
industrial	windowsdesktop-runtime-10-x64	windowsdesktop-runtime-10.0.9-win-x64.zip	https://builds.dotnet.microsoft.com/dotnet/WindowsDesktop/10.0.9/windowsdesktop-runtime-10.0.9-win-x64.zip	.NET Windows Desktop Runtime 10.0.9 win-x64 ZIP; WinForms/WPF payload paired with dotnet-runtime-10-x64 for modern desktop apphost samples.
industrial	ugs-cnc	ugs-2.1.23-x64.msi	https://github.com/winder/Universal-G-Code-Sender/releases/download/v2.1.23/ugs-2.1.23-x64.msi	Universal Gcode Sender x64 MSI; CNC control workflow, serial-port UI, JavaFX/Swing-adjacent runtime and G-code preview coverage.
industrial	energyplus-building	EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64.exe	https://github.com/NatLabRockies/EnergyPlus/releases/download/v26.1.0/EnergyPlus-26.1.0-6f2e40d102-Windows-x86_64.exe	EnergyPlus building energy simulation installer; engineering command tools, examples, path handling and large scientific payload coverage.
industrial	openjump-gis	OpenJUMP-Portable-2.4.0-r5303[6c9a02d]-PLUS.zip	https://sourceforge.net/projects/jump-pilot/files/OpenJUMP/2.4.0/OpenJUMP-Portable-2.4.0-r5303%5B6c9a02d%5D-PLUS.zip/download	OpenJUMP GIS portable ZIP; Java GIS workbench, vector editing, map rendering and no-install archive launch coverage.
industrial	opendss-svn-x64-comports	opendss-svn-x64/ComPorts.ini	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/ComPorts.ini	OpenDSS x64 beta runtime file from official SourceForge SVN; direct-copy fallback when the installer crashes under Wine.
industrial	opendss-svn-x64-progress	opendss-svn-x64/DSSProgress.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/DSSProgress.exe	OpenDSS x64 beta progress helper from official SourceForge SVN.
industrial	opendss-svn-x64-view	opendss-svn-x64/DSSView.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/DSSView.exe	OpenDSS x64 beta viewer helper from official SourceForge SVN.
industrial	opendss-svn-x64-indmach	opendss-svn-x64/IndMach012a.dll	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/IndMach012a.dll	OpenDSS x64 beta dynamic model DLL from official SourceForge SVN.
industrial	opendss-svn-x64-klusolve	opendss-svn-x64/KLUSolve.dll	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/KLUSolve.dll	OpenDSS x64 beta sparse solver DLL from official SourceForge SVN.
industrial	opendss-svn-x64-license	opendss-svn-x64/License.txt	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/License.txt	OpenDSS x64 beta license text from official SourceForge SVN.
industrial	opendss-svn-x64-gui	opendss-svn-x64/OpenDSS.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSS.exe	OpenDSS x64 beta GUI executable from official SourceForge SVN.
industrial	opendss-svn-x64-gui-rsm	opendss-svn-x64/OpenDSS.rsm	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSS.rsm	OpenDSS x64 beta GUI sidecar from official SourceForge SVN.
industrial	opendss-svn-x64-direct	opendss-svn-x64/OpenDSSDirect.dll	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSSDirect.dll	OpenDSS x64 beta direct DLL from official SourceForge SVN.
industrial	opendss-svn-x64-direct-header	opendss-svn-x64/OpenDSSDirect.h	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSSDirect.h	OpenDSS x64 beta direct API header from official SourceForge SVN.
industrial	opendss-svn-x64-cmd	opendss-svn-x64/OpenDSScmd.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSScmd.exe	OpenDSS x64 beta command-line simulator from official SourceForge SVN; headless power-system smoke target.
industrial	opendss-svn-x64-cmd-rsm	opendss-svn-x64/OpenDSScmd.rsm	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSScmd.rsm	OpenDSS x64 beta command-line sidecar from official SourceForge SVN.
industrial	opendss-svn-x64-engine	opendss-svn-x64/OpenDSSengine.dll	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/OpenDSSengine.dll	OpenDSS x64 beta engine DLL from official SourceForge SVN.
industrial	opendss-svn-x64-kmetis	opendss-svn-x64/kmetis.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/kmetis.exe	OpenDSS x64 beta METIS helper from official SourceForge SVN.
industrial	opendss-svn-x64-pmetis	opendss-svn-x64/pmetis.exe	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/pmetis.exe	OpenDSS x64 beta PMETIS helper from official SourceForge SVN.
industrial	opendss-svn-x64-readme	opendss-svn-x64/readme.txt	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/readme.txt	OpenDSS x64 beta readme from official SourceForge SVN.
industrial	opendss-svn-x64-testbat	opendss-svn-x64/testcommandline.bat	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/testcommandline.bat	OpenDSS x64 beta command-line test batch from official SourceForge SVN.
industrial	opendss-svn-x64-testdss	opendss-svn-x64/testcommandline.dss	https://svn.code.sf.net/p/electricdss/code/trunk/Version8/Distrib/x64/testcommandline.dss	OpenDSS x64 beta command-line test script from official SourceForge SVN.
graphics	inkscape	Inkscape-1.4.2-x64.msi	https://sourceforge.net/projects/inkscape/files/inkscape-1.4.2_2025-05-13_f4327f4-x64.msi/download	Vector drawing/technical illustration MSI.
graphics	blender	blender-4.1.0-windows-x64.msi	https://download.blender.org/release/Blender4.1/blender-4.1.0-windows-x64.msi	Blender 3D workstation; OpenGL viewport, Python startup and large MSI coverage.
graphics	gimp	GIMP-2.10.38-win64-setup.exe	https://download.gimp.org/gimp/v2.10/windows/gimp-2.10.38-setup.exe	GIMP image editor; GTK3 UI, tablet-adjacent input, plug-ins, large dialogs and font rendering; keeps the stable pre-revision installer because revision 1 currently fails innoextract.
graphics	gimp-revision1	gimp-2.10.38-setup-1.exe	https://download.gimp.org/gimp/v2.10/windows/gimp-2.10.38-setup-1.exe	GIMP 2.10.38 revision 1 installer retained as a negative extraction sample for Inno parser compatibility.
graphics	krita	krita-x64-5.2.9-setup.exe	https://download.kde.org/stable/krita/5.2.9/krita-x64-5.2.9-setup.exe	Digital painting workstation; Qt/OpenGL canvas, tablet-adjacent input and color/font rendering.
graphics	audacity	audacity-win-3.7.8-64bit.exe	https://github.com/audacity/audacity/releases/download/Audacity-3.7.8/audacity-win-3.7.8-64bit.exe	Audio editor sample; waveform rendering, audio device enumeration, plug-ins and file dialogs.
graphics	flameshot	Flameshot-14.0.0-win64.msi	https://github.com/flameshot-org/flameshot/releases/download/v14.0.0/Flameshot-14.0.0-win64.msi	Screenshot/annotation utility; global shortcut limits, Qt UI and tray behavior coverage.
graphics	musescore	MuseScore-Studio-4.7.3.260608135-x86_64.msi	https://github.com/musescore/MuseScore/releases/download/v4.7.3/MuseScore-Studio-4.7.3.260608135-x86_64.msi	Music notation workstation; Qt, audio/MIDI-adjacent paths, fonts and complex document canvas.
graphics	lmms	lmms-1.2.2-win64.exe	https://github.com/lmms/lmms/releases/download/v1.2.2/lmms-1.2.2-win64.exe	LMMS music production workstation; Qt/audio/MIDI-adjacent UI, plugin loading and timeline rendering coverage.
graphics	openshot	OpenShot-v3.3.0-x86_64.exe	https://github.com/OpenShot/openshot-qt/releases/download/v3.3.0/OpenShot-v3.3.0-x86_64.exe	OpenShot video editor; Qt timeline, media import dialogs, preview rendering and codec/runtime coverage.
utility	powertoys	PowerToysUserSetup-0.100.0-x64.exe	https://github.com/microsoft/PowerToys/releases/download/v0.100.0/PowerToysUserSetup-0.100.0-x64.exe	Windows utility suite stress sample; services, shell hooks and Windows-version API gaps.
utility	moonlight	MoonlightSetup-6.1.0.exe	https://github.com/moonlight-stream/moonlight-qt/releases/download/v6.1.0/MoonlightSetup-6.1.0.exe	Game-streaming client sample; Qt, video decode, controller input and networking UI.
utility	vscode	VSCodeUserSetup-x64-1.125.1.exe	https://update.code.visualstudio.com/latest/win32-x64-user/stable	Visual Studio Code user installer; Electron editor, extension host, terminal spawning and font rendering coverage.
utility	vscode-portable	VSCode-win32-x64-1.125.1.zip	https://code.visualstudio.com/sha/download?build=stable&os=win32-x64-archive	Visual Studio Code portable ZIP; no-install Electron app and archive extraction coverage.
utility	postman	Postman-win64-latest.exe	https://dl.pstmn.io/download/latest/win64	Postman API client; Electron app shell, TLS, proxy settings, large UI lists and native file dialogs.
utility	git-for-windows	Git-2.54.0-64-bit.exe	https://github.com/git-for-windows/git/releases/download/v2.54.0.windows.1/Git-2.54.0-64-bit.exe	Git for Windows; installer, console subprocesses, credential dialogs, PATH registration and terminal behavior.
utility	notepadpp	npp.8.9.6.4.Installer.x64.exe	https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.6.4/npp.8.9.6.4.Installer.x64.exe	Notepad++ native editor; Scintilla text rendering, plugins, file associations and ordinary Win32 UI coverage.
utility	notepadpp-32	npp.8.9.6.4.Installer.exe	https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.9.6.4/npp.8.9.6.4.Installer.exe	Notepad++ 32-bit installer; WOW64 Scintilla editor, plugins and file association coverage.
utility	autohotkey	AutoHotkey_2.0.26_setup.exe	https://github.com/AutoHotkey/AutoHotkey/releases/download/v2.0.26/AutoHotkey_2.0.26_setup.exe	AutoHotkey v2 installer; hotkey hook limits, script runtime, tray behavior and shell integration coverage.
utility	putty	putty-64bit-installer.msi	https://the.earth.li/~sgtatham/putty/latest/w64/putty-64bit-installer.msi	PuTTY terminal client; classic Win32 dialogs, networking UI, fonts and MSI coverage.
utility	winscp	WinSCP-6.5.6-Setup.exe	https://winscp.net/download/WinSCP-6.5.6-Setup.exe/download	WinSCP file-transfer client; SFTP/SCP dialogs, shell integration, credential UI, drag/drop and TLS coverage.
utility	winscp-x64-experimental	WinSCP-6.6.2.RC-Portable-x64-Experimental.zip	https://winscp.net/download/WinSCP-6.6.2.RC-Portable-x64-Experimental.zip/download	WinSCP experimental x64 portable executables; validates native x64 GUI/CLI file-transfer behavior while the stable 32-bit VCL GUI remains a WOW64 SEH regression sample.
utility	keepass	KeePass-2.59-Setup.exe	https://sourceforge.net/projects/keepass/files/KeePass%202.x/2.59/KeePass-2.59-Setup.exe/download	KeePass password manager sample; WinForms, secure text fields, file dialogs and mono/.NET-adjacent controls.
utility	keepassxc	KeePassXC-2.7.12-Win64.msi	https://github.com/keepassxreboot/keepassxc/releases/download/2.7.12/KeePassXC-2.7.12-Win64.msi	KeePassXC x64 MSI; Qt password manager, secure text fields, browser-integration settings and file dialogs.
utility	espanso	Espanso-Win-Installer-x86_64.exe	https://github.com/espanso/espanso/releases/download/v2.3.0/Espanso-Win-Installer-x86_64.exe	Espanso text expander; background service/tray behavior, global hooks and installer/runtime permission coverage.
utility	qbittorrent	qbittorrent_5.2.2_x64_setup.exe	https://github.com/qbittorrent/qBittorrent/releases/download/release-5.2.2/qbittorrent_5.2.2_x64_setup.exe	qBittorrent network utility; Qt lists, TLS, tray behavior and network settings coverage.
utility	everything	Everything-1.4.1.1028.x64-Setup.exe	https://www.voidtools.com/Everything-1.4.1.1028.x64-Setup.exe	Everything file search; indexing service, shell integration, list rendering and small Win32 utility coverage.
utility	7zip	7z2601-x64.exe	https://www.7-zip.org/a/7z2601-x64.exe	7-Zip file archiver; compact Win32 UI, shell integration, file association and archive extraction coverage.
utility	obs-studio	OBS-Studio-32.1.2-Windows-x64-Installer.exe	https://github.com/obsproject/obs-studio/releases/download/32.1.2/OBS-Studio-32.1.2-Windows-x64-Installer.exe	OBS Studio installer; media device enumeration, GPU capture fallbacks and complex settings UI.
utility	rufus	rufus-4.11.exe	https://github.com/pbatard/rufus/releases/download/v4.11/rufus-4.11.exe	Rufus USB imaging utility; compact Win32 UI, privilege/device API gaps and single-exe launch coverage.
utility	winmerge	WinMerge-2.16.50-x64-Setup.exe	https://github.com/WinMerge/winmerge/releases/download/v2.16.50/WinMerge-2.16.50-x64-Setup.exe	WinMerge diff/merge tool; native file tree, text editor, shell integration and installer coverage.
utility	q-dir	Q-Dir_Installer_x64.zip	https://www.softwareok.com/Download/Q-Dir_Installer_x64.zip	Q-Dir file manager; classic Win32 multi-pane shell/file dialogs and ZIP installer coverage.
EOF

printf 'Started %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOG"

ok=0
failed=0
while IFS=$'\t' read -r category id file_name url notes; do
  if [ "$category" = "category" ]; then
    continue
  fi
  if ! should_download "$category" "$id" "$notes"; then
    continue
  fi
  if download_one "$id" "$category" "$file_name" "$url" "$notes"; then
    ok=$((ok + 1))
  else
    failed=$((failed + 1))
  fi
done < "$MANIFEST"

printf 'Finished ok=%s failed=%s downloads=%s\n' "$ok" "$failed" "$DOWNLOADS" | tee -a "$LOG"
exit 0
