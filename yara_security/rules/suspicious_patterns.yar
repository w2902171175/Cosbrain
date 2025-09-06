/*
    YARA规则 - 可疑模式检测
    用于检测可疑的文件模式和行为
*/

rule Suspicious_File_Size
{
    meta:
        description = "检测异常大小的文件"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "low"
        
    condition:
        filesize > 100MB or filesize == 0
}

rule Base64_Encoded_Content
{
    meta:
        description = "检测Base64编码内容"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "low"
        
    strings:
        $base64_1 = /[A-Za-z0-9+\/]{100,}={0,2}/
        $base64_header = "data:image/jpeg;base64,"
        $base64_header2 = "data:image/png;base64,"
        
    condition:
        $base64_1 and not any of ($base64_header*)
}

rule Obfuscated_Javascript
{
    meta:
        description = "检测混淆的JavaScript代码"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $js_1 = "eval("
        $js_2 = "unescape("
        $js_3 = "String.fromCharCode("
        $js_4 = "document.write("
        $obfuscation_1 = /var\s+[a-zA-Z_$][a-zA-Z0-9_$]*\s*=\s*['"][^'"]{50,}['"]/
        
    condition:
        2 of ($js_*) and $obfuscation_1
}

rule Suspicious_PowerShell
{
    meta:
        description = "检测可疑的PowerShell命令"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "high"
        
    strings:
        $ps_1 = "-EncodedCommand" nocase
        $ps_2 = "-WindowStyle Hidden" nocase
        $ps_3 = "-ExecutionPolicy Bypass" nocase
        $ps_4 = "DownloadString" nocase
        $ps_5 = "DownloadFile" nocase
        $ps_6 = "IEX" nocase
        $ps_7 = "Invoke-Expression" nocase
        $ps_8 = "New-Object Net.WebClient" nocase
        
    condition:
        3 of them
}

rule Suspicious_Registry_Operations
{
    meta:
        description = "检测可疑的注册表操作"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $reg_1 = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $reg_2 = "HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" nocase
        $reg_3 = "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services" nocase
        $reg_4 = "DisableAntiSpyware" nocase
        $reg_5 = "DisableRealtimeMonitoring" nocase
        
    condition:
        any of them
}

rule Suspicious_Network_Activity
{
    meta:
        description = "检测可疑的网络活动"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $net_1 = "nc.exe" nocase
        $net_2 = "netcat" nocase
        $net_3 = "telnet" nocase
        $net_4 = /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}/
        $net_5 = "bind shell" nocase
        $net_6 = "reverse shell" nocase
        
    condition:
        2 of them
}

rule Suspicious_File_Operations
{
    meta:
        description = "检测可疑的文件操作"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $file_1 = "attrib +h" nocase  // 隐藏文件
        $file_2 = "icacls" nocase     // 修改权限
        $file_3 = "takeown" nocase    // 获取所有权
        $file_4 = "sfc /scannow" nocase
        $file_5 = "vssadmin delete shadows" nocase  // 删除卷影副本
        $file_6 = "wbadmin delete catalog" nocase
        
    condition:
        2 of them
}

rule Packed_Executable
{
    meta:
        description = "检测打包的可执行文件"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $mz = {4D 5A}
        $upx = "UPX"
        $aspack = "aPLib"
        $pecompact = "PECompact"
        $fsg = "FSG"
        $nspack = "NsPack"
        
    condition:
        $mz at 0 and any of ($upx, $aspack, $pecompact, $fsg, $nspack)
}

rule Suspicious_PDF_Content
{
    meta:
        description = "检测可疑的PDF内容"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $pdf_header = "%PDF"
        $js = "/JavaScript" nocase
        $js2 = "/JS" nocase
        $openaction = "/OpenAction" nocase
        $launch = "/Launch" nocase
        $embed = "/EmbeddedFile" nocase
        
    condition:
        $pdf_header at 0 and (2 of ($js, $js2, $openaction, $launch, $embed))
}

rule Multiple_Extensions
{
    meta:
        description = "检测多重扩展名文件"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    condition:
        // 文件名包含多个扩展名，如 document.pdf.exe
        filename matches /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|jpg|png|gif)\.(exe|scr|bat|cmd|com|pif)$/i
}

rule Suspicious_Archives_Content
{
    meta:
        description = "检测压缩文件中的可疑内容"
        author = "Security Team" 
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $zip = {50 4B 03 04}
        $rar = {52 61 72 21}
        $password_protected = "encrypted"
        $suspicious_filename = ".exe"
        $suspicious_filename2 = ".scr"
        $suspicious_filename3 = ".bat"
        
    condition:
        ($zip at 0 or $rar at 0) and 
        ($password_protected or any of ($suspicious_filename*))
}

rule Long_Domain_Names
{
    meta:
        description = "检测异常长的域名"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "low"
        
    strings:
        $domain = /https?:\/\/[a-zA-Z0-9\-\.]{50,}/
        
    condition:
        $domain
}

rule Suspicious_Email_Attachments
{
    meta:
        description = "检测可疑的邮件附件模式"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "medium"
        
    strings:
        $attachment_1 = "Content-Disposition: attachment"
        $attachment_2 = "filename="
        $suspicious_ext_1 = ".exe"
        $suspicious_ext_2 = ".scr"
        $suspicious_ext_3 = ".bat"
        $suspicious_ext_4 = ".cmd"
        $suspicious_ext_5 = ".com"
        $suspicious_ext_6 = ".pif"
        $suspicious_ext_7 = ".vbs"
        $suspicious_ext_8 = ".js"
        
    condition:
        $attachment_1 and $attachment_2 and any of ($suspicious_ext_*)
}

rule Cryptocurrency_Wallet_Addresses
{
    meta:
        description = "检测加密货币钱包地址"
        author = "Security Team"
        date = "2024-01-01"
        threat_level = "low"
        
    strings:
        // Bitcoin地址模式
        $bitcoin = /[13][a-km-zA-HJ-NP-Z1-9]{25,34}/
        // Ethereum地址模式
        $ethereum = /0x[a-fA-F0-9]{40}/
        // Monero地址模式
        $monero = /4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}/
        
    condition:
        any of them
}
