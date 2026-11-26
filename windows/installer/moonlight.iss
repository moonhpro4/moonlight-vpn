; Inno Setup script for Moonlight VPN (Windows)
; Built by .github/workflows/build-windows.yml  ->  windows/out/MoonlightVPN-Setup.exe
#define AppName "Moonlight VPN"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F0B7C0E-5D0A-4B7B-9E54-4D6F4C1A0A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=moonhpro4
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\out
OutputBaseFilename=MoonlightVPN-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\MoonlightVPN.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\MoonlightVPN\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; The OpenVPN engine installer is bundled when the CI build could download it.
#ifexist "openvpn.msi"
Source: "openvpn.msi"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not OpenVpnInstalled
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\MoonlightVPN.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MoonlightVPN.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
; 1) OpenVPN engine: bundled MSI first ...
#ifexist "openvpn.msi"
Filename: "msiexec.exe"; Parameters: "/i ""{tmp}\openvpn.msi"" /qn /norestart"; StatusMsg: "Installing the OpenVPN engine..."; Flags: waituntilterminated; Check: not OpenVpnInstalled
#endif
; ... otherwise (or if that failed) winget
Filename: "{cmd}"; Parameters: "/c winget install -e --id OpenVPNTechnologies.OpenVPN --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Installing the OpenVPN engine (winget)..."; Flags: runhidden waituntilterminated; Check: not OpenVpnInstalled
; 2) "Moonlight VPN" entry in the Windows VPN list + start-with-Windows + Windows-VPN-button tasks
Filename: "{app}\MoonlightVPN.exe"; Parameters: "--install-integration"; StatusMsg: "Adding Moonlight VPN to the Windows VPN list..."; Flags: runhidden waituntilterminated
; 3) open the app
Filename: "{app}\MoonlightVPN.exe"; Description: "Open Moonlight VPN"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\MoonlightVPN.exe"; Parameters: "--remove-integration"; RunOnceId: "RemoveIntegration"; Flags: runhidden waituntilterminated

[Code]
function OpenVpnInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf64}\OpenVPN\bin\openvpn.exe'))
         or FileExists(ExpandConstant('{commonpf32}\OpenVPN\bin\openvpn.exe'));
end;
