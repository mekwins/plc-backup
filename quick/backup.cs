// Quick & dirty PLC backup — single file, .NET 8, Windows only.
// Requires: Rockwell Logix Designer SDK installed on this machine.
//
// Build & run:
//   dotnet script backup.cs          (with dotnet-script tool)
// OR compile:
//   csc backup.cs   (or add to a .csproj and dotnet run)
//
// Edit the constants at the top, then run.

using System;
using System.IO;
using System.Threading.Tasks;

// ---------------------------------------------------------------------------
// EDIT THESE CONSTANTS
// ---------------------------------------------------------------------------
const string PLC_NAME      = "Line01-CellA-Main";
const string PLC_COMM_PATH = @"AB_ETHIP-1\10.40.12.15\Backplane\0";
const string OUTPUT_DIR    = @"C:\PLCBackups\quick";
// ---------------------------------------------------------------------------

await RunBackupAsync();

static async Task RunBackupAsync()
{
    // Check that we are on Windows — the Rockwell SDK is Windows-only.
    if (!OperatingSystem.IsWindows())
    {
        Console.Error.WriteLine("ERROR: Rockwell Logix Designer SDK requires Windows.");
        Environment.Exit(1);
    }

    string timestamp = DateTime.UtcNow.ToString("yyyy-MM-ddTHH-mm-ssZ");
    string outDir    = Path.Combine(OUTPUT_DIR, PLC_NAME, timestamp);
    Directory.CreateDirectory(outDir);

    string acdPath = Path.Combine(outDir, $"{PLC_NAME}.ACD");
    string l5xPath = Path.Combine(outDir, $"{PLC_NAME}.L5X");

    Console.WriteLine($"[{DateTime.UtcNow:u}] Connecting to {PLC_NAME} via {PLC_COMM_PATH}");

    // ---------------------------------------------------------------------------
    // Rockwell Logix Designer SDK usage via .NET.
    //
    // Reference the SDK assembly — adjust path to match your installation:
    //   C:\Program Files (x86)\Rockwell Software\Logix Designer SDK\...
    //
    // The SDK exposes a COM/interop or managed interface depending on version.
    // The block below shows the documented interaction pattern.
    // Confirm exact method names against the C# examples shipped with the SDK at:
    //   C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\Examples
    // ---------------------------------------------------------------------------

    // Pseudo-code matching the documented SDK pattern:
    //
    // using var project = await LogixProject.OpenLogixProjectAsync(acdPath);
    // await project.SetCommunicationsPathAsync(PLC_COMM_PATH);
    // await project.SaveAsync();
    // await project.ExportL5XAsync(l5xPath);
    // await project.CloseAsync();
    //
    // Replace the simulation block below with real SDK calls once references are set up.

    Console.WriteLine($"[{DateTime.UtcNow:u}] Saving ACD  -> {acdPath}");
    Console.WriteLine($"[{DateTime.UtcNow:u}] NOTE: replace simulation with real SDK calls.");

    // Simulation: write placeholder files so the directory structure is visible.
    await File.WriteAllTextAsync(acdPath, $"PLACEHOLDER ACD — {PLC_NAME} — {timestamp}");
    await File.WriteAllTextAsync(l5xPath,
        $"""
        <?xml version="1.0" encoding="UTF-8"?>
        <!-- PLACEHOLDER L5X — {PLC_NAME} — {timestamp} -->
        <RSLogix5000Content SchemaRevision="1.0">
          <Controller Name="{PLC_NAME}" />
        </RSLogix5000Content>
        """);

    Console.WriteLine($"[{DateTime.UtcNow:u}] Exporting L5X -> {l5xPath}");
    Console.WriteLine($"[{DateTime.UtcNow:u}] Done. Files written to {outDir}");
}
