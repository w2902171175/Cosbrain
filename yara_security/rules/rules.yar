/*
    强化版YARA安全规则库 v2.0
    创建时间: 2025-08-29
    描述: 全面的文件安全检测规则，覆盖最新威胁
*/

// ===== 高危恶意软件检测 =====

rule Advanced_Ransomware_Detection
{
    meta:
        description = "检测勒索软件特征"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "ransomware"
        
    strings:
        $ransom1 = "encrypted" nocase
        $ransom2 = "decrypt" nocase
        $ransom3 = "bitcoin" nocase
        $ransom4 = "payment" nocase
        $ransom5 = "ransom" nocase
        $ransom6 = "restore your files" nocase
        $ransom7 = "all your files" nocase
        $ransom8 = ".locked" nocase
        $ransom9 = ".encrypted" nocase
        $ransom10 = "README_FOR_DECRYPT" nocase
        $ransom11 = "HOW_TO_DECRYPT" nocase
        $ransom12 = "YOUR_FILES_ARE_ENCRYPTED" nocase
        
        $api1 = "CryptEncrypt" nocase
        $api2 = "CryptGenKey" nocase
        $api3 = "FindFirstFile" nocase
        $api4 = "FindNextFile" nocase
        
    condition:
        (3 of ($ransom*)) or (2 of ($api*) and 1 of ($ransom*))
}

rule Advanced_Backdoor_Detection
{
    meta:
        description = "检测后门和远程访问木马"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "backdoor"
        
    strings:
        $backdoor1 = "remote control" nocase
        $backdoor2 = "keylogger" nocase
        $backdoor3 = "screen capture" nocase
        $backdoor4 = "file manager" nocase
        $backdoor5 = "reverse shell" nocase
        $backdoor6 = "backdoor" nocase
        $backdoor7 = "remote access" nocase
        $backdoor8 = "rat" nocase
        $backdoor9 = "trojan" nocase
        
        $net1 = "socket" nocase
        $net2 = "connect" nocase
        $net3 = "send" nocase
        $net4 = "recv" nocase
        $net5 = "WSAStartup" nocase
        
        $sys1 = "CreateProcess" nocase
        $sys2 = "ShellExecute" nocase
        $sys3 = "WinExec" nocase
        $sys4 = "GetSystemDirectory" nocase
        
    condition:
        (2 of ($backdoor*)) or 
        (1 of ($backdoor*) and 2 of ($net*)) or
        (1 of ($backdoor*) and 2 of ($sys*))
}

rule Cryptocurrency_Miner_Detection
{
    meta:
        description = "检测加密货币挖矿软件"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "cryptominer"
        
    strings:
        $crypto1 = "bitcoin" nocase
        $crypto2 = "ethereum" nocase
        $crypto3 = "monero" nocase
        $crypto4 = "mining" nocase
        $crypto5 = "miner" nocase
        $crypto6 = "pool" nocase
        $crypto7 = "hashrate" nocase
        $crypto8 = "difficulty" nocase
        $crypto9 = "stratum" nocase
        $crypto10 = "xmrig" nocase
        $crypto11 = "cryptonight" nocase
        $crypto12 = "nicehash" nocase
        
    condition:
        3 of them
}

// ===== 脚本威胁检测 =====

rule Malicious_PowerShell_Detection
{
    meta:
        description = "检测恶意PowerShell脚本"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "malicious_script"
        
    strings:
        $ps1 = "Invoke-Expression" nocase
        $ps2 = "DownloadString" nocase
        $ps3 = "EncodedCommand" nocase
        $ps4 = "FromBase64String" nocase
        $ps5 = "Hidden" nocase
        $ps6 = "WindowStyle" nocase
        $ps7 = "ExecutionPolicy" nocase
        $ps8 = "Bypass" nocase
        $ps9 = "Unrestricted" nocase
        $ps10 = "powershell.exe" nocase
        $ps11 = "Start-Process" nocase
        $ps12 = "New-Object" nocase
        $ps13 = "System.Net.WebClient" nocase
        $ps14 = "Invoke-WebRequest" nocase
        $ps15 = "iwr" nocase
        $ps16 = "curl" nocase
        $ps17 = "wget" nocase
        
    condition:
        3 of them
}

rule JavaScript_Obfuscation_Detection
{
    meta:
        description = "检测混淆的恶意JavaScript"
        author = "Security Team"
        date = "2025-08-29"
        severity = "medium"
        threat_type = "obfuscated_script"
        
    strings:
        $js1 = "eval(" nocase
        $js2 = "unescape(" nocase
        $js3 = "String.fromCharCode" nocase
        $js4 = "document.write" nocase
        $js5 = "innerHTML" nocase
        $js6 = "createElement" nocase
        $js7 = "appendChild" nocase
        
    condition:
        4 of them
}

rule PHP_Webshell_Detection
{
    meta:
        description = "检测PHP WebShell"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "webshell"
        
    strings:
        $php1 = "eval(" nocase
        $php2 = "exec(" nocase
        $php3 = "system(" nocase
        $php4 = "shell_exec(" nocase
        $php5 = "passthru(" nocase
        $php6 = "assert(" nocase
        $php7 = "file_get_contents(" nocase
        $php8 = "file_put_contents(" nocase
        $php9 = "fwrite(" nocase
        $php10 = "fputs(" nocase
        
        $shell1 = "<?php" nocase
        $shell2 = "$_GET[" nocase
        $shell3 = "$_POST[" nocase
        $shell4 = "$_REQUEST[" nocase
        $shell5 = "base64_decode(" nocase
        
    condition:
        $shell1 and (2 of ($php*) and 1 of ($shell2, $shell3, $shell4, $shell5))
}

// ===== 钓鱼和社会工程学检测 =====

rule Phishing_Content_Detection
{
    meta:
        description = "检测钓鱼内容"
        author = "Security Team"
        date = "2025-08-29"
        severity = "medium"
        threat_type = "phishing"
        
    strings:
        $phish1 = "verify your account" nocase
        $phish2 = "suspended account" nocase
        $phish3 = "click here to verify" nocase
        $phish4 = "urgent action required" nocase
        $phish5 = "confirm your identity" nocase
        $phish6 = "update your information" nocase
        $phish7 = "security alert" nocase
        $phish8 = "unusual activity" nocase
        $phish9 = "login credentials" nocase
        $phish10 = "credit card" nocase
        $phish11 = "bank account" nocase
        $phish12 = "paypal" nocase
        $phish13 = "amazon" nocase
        $phish14 = "microsoft" nocase
        $phish15 = "google" nocase
        
    condition:
        3 of them
}

// ===== 可疑网络活动检测 =====

rule Suspicious_Network_Activity
{
    meta:
        description = "检测可疑网络活动"
        author = "Security Team"
        date = "2025-08-29"
        severity = "medium"
        threat_type = "network_activity"
        
    strings:
        $net1 = "URLDownloadToFile" nocase
        $net2 = "InternetOpenUrl" nocase
        $net3 = "HttpSendRequest" nocase
        $net4 = "WinHttpOpen" nocase
        $net5 = "socket" nocase
        $net6 = "connect" nocase
        $net7 = "WSAConnect" nocase
        
    condition:
        3 of them
}

rule C2_Communication_Detection
{
    meta:
        description = "检测C&C通信特征"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "c2_communication"
        
    strings:
        $c2_1 = "POST" nocase
        $c2_2 = "GET" nocase
        $c2_3 = "User-Agent:" nocase
        $c2_4 = "Content-Type:" nocase
        $c2_5 = "application/x-www-form-urlencoded" nocase
        $c2_6 = "heartbeat" nocase
        $c2_7 = "beacon" nocase
        $c2_8 = "checkin" nocase
        $c2_9 = "command" nocase
        $c2_10 = "control" nocase
        
        $enc1 = "base64" nocase
        $enc2 = "encrypt" nocase
        $enc3 = "decrypt" nocase
        $enc4 = "AES" nocase
        $enc5 = "RC4" nocase
        
    condition:
        (3 of ($c2_*) and 1 of ($enc*)) or 5 of ($c2_*)
}

// ===== 文件类型和结构检测 =====

rule Packed_Executable_Detection
{
    meta:
        description = "检测加壳的可执行文件"
        author = "Security Team"
        date = "2025-08-29"
        severity = "medium"
        threat_type = "packed_executable"
        
    strings:
        $upx = "UPX!" 
        $mpress = "MPRESS"
        $aspack = "aPlib"
        $pecompact = "PECompact"
        $nspack = "NsPack"
        $fsg = "FSG"
        $pex = "PEX"
        
    condition:
        any of them
}

// ===== 持久化机制检测 =====

rule Registry_Persistence_Detection
{
    meta:
        description = "检测注册表持久化机制"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "persistence"
        
    strings:
        $reg1 = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $reg2 = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\RunOnce" nocase
        $reg3 = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Windows" nocase
        $reg4 = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" nocase
        $reg5 = "SYSTEM\\CurrentControlSet\\Services" nocase
        
        $regapi1 = "RegOpenKey" nocase
        $regapi2 = "RegSetValue" nocase
        $regapi3 = "RegCreateKey" nocase
        $regapi4 = "RegQueryValue" nocase
        
    condition:
        1 of ($reg*) and 1 of ($regapi*)
}

rule Service_Installation_Detection
{
    meta:
        description = "检测恶意服务安装"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "service_persistence"
        
    strings:
        $svc1 = "CreateService" nocase
        $svc2 = "OpenSCManager" nocase
        $svc3 = "StartService" nocase
        $svc4 = "ControlService" nocase
        $svc5 = "QueryServiceStatus" nocase
        
        $cfg1 = "SERVICE_AUTO_START" nocase
        $cfg2 = "SERVICE_DEMAND_START" nocase
        $cfg3 = "SERVICE_WIN32_OWN_PROCESS" nocase
        
    condition:
        2 of ($svc*) and 1 of ($cfg*)
}

// ===== 沙箱逃逸检测 =====

rule Sandbox_Evasion_Detection
{
    meta:
        description = "检测沙箱逃逸技术"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "evasion"
        
    strings:
        $vm1 = "VMware" nocase
        $vm2 = "VirtualBox" nocase
        $vm3 = "VBOX" nocase
        $vm4 = "QEMU" nocase
        $vm5 = "Xen" nocase
        
        $sb1 = "sandboxie" nocase
        $sb2 = "joe sandbox" nocase
        $sb3 = "cuckoo" nocase
        $sb4 = "anubis" nocase
        $sb5 = "threatanalyzer" nocase
        
        $tool1 = "wireshark" nocase
        $tool2 = "ollydbg" nocase
        $tool3 = "ida" nocase
        $tool4 = "processhacker" nocase
        $tool5 = "sysinternals" nocase
        
    condition:
        2 of them
}

// ===== 信息窃取检测 =====

rule Credential_Theft_Detection
{
    meta:
        description = "检测凭据窃取行为"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "credential_theft"
        
    strings:
        $chrome = "Chrome\\User Data\\Default\\Login Data" nocase
        $firefox = "Firefox\\Profiles" nocase
        $edge = "Edge\\User Data\\Default\\Login Data" nocase
        
        $pwd1 = "password" nocase
        $pwd2 = "credential" nocase
        $pwd3 = "login" nocase
        $pwd4 = "username" nocase
        $pwd5 = "autofill" nocase
        
        $crypt1 = "CryptUnprotectData" nocase
        $crypt2 = "CryptProtectData" nocase
        
    condition:
        (1 of ($chrome, $firefox, $edge) and 1 of ($pwd*)) or
        (2 of ($pwd*) and 1 of ($crypt*))
}

rule Keylogger_Detection
{
    meta:
        description = "检测键盘记录器"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "keylogger"
        
    strings:
        $hook1 = "SetWindowsHookEx" nocase
        $hook2 = "WH_KEYBOARD_LL" nocase
        $hook3 = "WH_KEYBOARD" nocase
        $hook4 = "GetKeyState" nocase
        $hook5 = "GetAsyncKeyState" nocase
        
        $key1 = "keylogger" nocase
        $key2 = "keystroke" nocase
        $key3 = "keyboard" nocase
        $key4 = "VK_" nocase
        
    condition:
        2 of ($hook*) or (1 of ($hook*) and 1 of ($key*))
}

// ===== 最新威胁检测 =====

rule Supply_Chain_Attack_Detection
{
    meta:
        description = "检测供应链攻击特征"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "supply_chain"
        
    strings:
        $npm1 = "npm install" nocase
        $npm2 = "package.json" nocase
        $pip1 = "pip install" nocase
        $pip2 = "requirements.txt" nocase
        $gem1 = "gem install" nocase
        
        $download1 = "curl -s" nocase
        $download2 = "wget -q" nocase
        $download3 = "Invoke-WebRequest" nocase
        
        $exec1 = "eval" nocase
        $exec2 = "exec" nocase
        $exec3 = "system" nocase
        
    condition:
        (1 of ($npm*, $pip*, $gem*) and 1 of ($download*) and 1 of ($exec*))
}

rule Living_Off_The_Land_Detection
{
    meta:
        description = "检测利用系统工具的攻击"
        author = "Security Team"
        date = "2025-08-29"
        severity = "high"
        threat_type = "lolbins"
        
    strings:
        $tool1 = "certutil" nocase
        $tool2 = "bitsadmin" nocase
        $tool3 = "regsvr32" nocase
        $tool4 = "rundll32" nocase
        $tool5 = "mshta" nocase
        $tool6 = "cscript" nocase
        $tool7 = "wscript" nocase
        $tool8 = "powershell" nocase
        $tool9 = "cmd.exe" nocase
        
        $param1 = "-decode" nocase
        $param2 = "-split" nocase
        $param3 = "-f" nocase
        $param4 = "/c" nocase
        $param5 = "/k" nocase
        $param6 = "-enc" nocase
        $param7 = "-w hidden" nocase
        
    condition:
        1 of ($tool*) and 1 of ($param*)
}

rule Fileless_Malware_Detection
{
    meta:
        description = "检测无文件恶意软件特征"
        author = "Security Team"
        date = "2025-08-29"
        severity = "critical"
        threat_type = "fileless"
        
    strings:
        $mem1 = "VirtualAlloc" nocase
        $mem2 = "VirtualProtect" nocase
        $mem3 = "WriteProcessMemory" nocase
        $mem4 = "ReadProcessMemory" nocase
        $mem5 = "CreateRemoteThread" nocase
        
        $inj1 = "SetThreadContext" nocase
        $inj2 = "GetThreadContext" nocase
        $inj3 = "ResumeThread" nocase
        $inj4 = "SuspendThread" nocase
        $inj5 = "QueueUserAPC" nocase
        
        $wmi1 = "Win32_Process" nocase
        $wmi2 = "Create" nocase
        $wmi3 = "WScript.Shell" nocase
        
    condition:
        (2 of ($mem*) and 1 of ($inj*)) or 
        (2 of ($wmi*))
}
