# Quick PLC Backup Scripts — How to Use

Two standalone scripts that connect to a Rockwell Logix PLC, save an ACD file,
and export an L5X file. Both are Windows-only (Rockwell SDK requirement).

---

## Step 1 — Edit the constants

Open the script you want to use and change the three constants at the top:

| Constant | What it is | Example |
|---|---|---|
| `PLC_NAME` | Friendly name for the controller | `Line01-CellA-Main` |
| `PLC_COMM_PATH` | FactoryTalk Linx communication path | `AB_ETHIP-1\10.40.12.15\Backplane\0` |
| `OUTPUT_DIR` | Local folder where files are saved | `C:\PLCBackups\quick` |

The communication path must match exactly what appears in the **FactoryTalk Linx
Network Browser** on the backup machine.

---

## Python version — `backup.py`

### Prerequisites

- Windows 10/11 or Windows Server 2022
- Python 3.12 or later
- Studio 5000 Logix Designer version 33+
- Logix Designer SDK version 2.01+
- FactoryTalk Linx installed and running
- SDK Python wheel installed:

```
pip install "C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python\Examples\logix_designer_sdk-2.0.1-py3-none-any.whl"
```

(Adjust the wheel filename to the version installed on your machine.)

### Run

```
python backup.py
```

### Output

```
C:\PLCBackups\quick\
  Line01-CellA-Main\
    2026-03-18T21-15-00Z\
      Line01-CellA-Main.ACD
      Line01-CellA-Main.L5X
```

---

## .NET version — `backup.cs`

### Prerequisites

- Windows 10/11 or Windows Server 2022
- .NET 8 SDK
- Studio 5000 Logix Designer version 33+
- Logix Designer SDK version 2.01+
- FactoryTalk Linx installed and running

### Option A — dotnet-script (no project file needed)

```
dotnet tool install -g dotnet-script
dotnet script backup.cs
```

### Option B — compile with csc

```
csc backup.cs
backup.exe
```

### Option C — add to a project

Create a minimal `.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
</Project>
```

Then:
```
dotnet run
```

### SDK reference (before running for real)

The `.cs` file currently writes placeholder files. To make it call the real SDK,
add a reference to the Rockwell SDK assembly (path varies by installation):

```
C:\Program Files (x86)\Rockwell Software\Logix Designer SDK\...
```

Then replace the simulation block with the real SDK calls shown in the comments.
Confirm exact method names from the C# examples shipped with the SDK:

```
C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\Examples\
```

---

## SDK method note (both versions)

The exact `upload-to-new-project` method signature must be confirmed from the
installed SDK examples on your deployment machine. The scripts follow the
documented interaction pattern but the precise call may differ between SDK
versions.
