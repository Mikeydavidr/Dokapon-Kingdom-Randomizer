using System.Text.RegularExpressions;

namespace DokaponKingdomRandomizer
{
    internal class Randomizer
    {
        // Data Offsets (stageBase_EN.DAT, Steam/PC only)
        // [0] = builds before the October 2025 update (the Chinese language patch)
        // [1] = the current build. The update re-encoded some text as UTF-8, so every offset after the first few KB moved.
        // The two builds are told apart by file size, see GameBuildBySize.

        // Version Number
        private static string RandomVersion = "3.0";

        // Base File
        public static string FileBase = "stageBase_EN.DAT";
        public static readonly long[] FileSizeByBuild = new long[2] { 725136, 725600 };

        // Shop Items
        public static int[] LocShopEquipment = new int[2] { 0x5054, 0x5068 };
        public static int[] LocShopConsumables = new int[2] { 0x5100, 0x5114 };
        public static int[] LocShopMagic = new int[2] { 0x51A4, 0x51B8 };
        // Drop Items
        public static int[] LocDropsMonsters = new int[2] { 0x1C500, 0x1C58C };
        public static int[] LocDropsSpaces = new int[2] { 0x3CDC, 0x3CF0 };
        // Item Stats
        public static int[] LocStatsWeapons = new int[2] { 0x83CC, 0x83F0 };
        public static int[] LocStatsShields = new int[2] { 0xAB48, 0xAB7C };
        public static int[] LocStatsAccessories = new int[2] { 0xBDAC, 0xBDE4 };
        public static int[] LocStatsConsumables = new int[2] { 0xDF7C, 0xDFB4 };
        public static int[] LocStatsGifts = new int[2] { 0xE760, 0xE7A0 };
        public static int[] LocStatsMagicOffense = new int[2] { 0x14C4C, 0x14C94 };
        public static int[] LocStatsMagicDefense = new int[2] { 0x14EFC, 0x14F44 };
        public static int[] LocStatsMagicField = new int[2] { 0x15150, 0x15198 };
        // Unit Stats
        public static int[] LocStatsClassesBase = new int[2] { 0x184A8, 0x18508 };
        public static int[] LocStatsClassesLevelups = new int[2] { 0x18608, 0x18668 };
        public static int[] LocStatsClassesSalary = new int[2] { 0x18A08, 0x18A68 };
        public static int[] LocStatsClassesCapacity = new int[2] { 0x188A8, 0x18908 };
        public static int[] LocStatsMonsters = new int[2] { 0x1B0B0, 0x1B13C };
        // Prank Names
        public static int[] LocPrankNames = new int[2] { 0x4B73C, 0x4B8EC };

        // Equipment table regexes (shared by RandomizeEquip and ShuffleEquip)
        // I'm not going to explain the Regex here, it's complicated.
        private static readonly Regex rgx_weapons = new("(?s)(\\x58\\x00\\x00\\x00)([\\s\\S])([\\s\\S])([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)(\\x00\\x00?\\x00?\\x00?)([\\s\\S]{4})([\\s\\S]{4})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})");
        private static readonly Regex rgx_shields = new("(?s)(\\^[\\x00\\s]{3})([\\x01-\\x28])([\\s\\S])([\\s\\S]{2})((Demon Shield)[\\x00\\s\\S]{6,10}|([0-9A-Za-z\\+\\'\\-]+( Guard| Shield)?)([\\x00\\s]{8}|[\\x00\\s]{7}|[\\x00\\s]{6}|[\\x00\\s]{3}[\\x01-\\xff][\\x00\\s]{2}|[\\x00\\s]{1,3}[\\x01-\\xff]{2}[\\x00\\s]{2}|[\\x00\\s][\\x01-\\xff]{2}[\\x00\\s]{2}|[\\x00\\s]{0,3}[\\S\\x01-\\xFF]{0,3}?[\\x00\\s]{0,3}))([\\x00\\s\\S]{3}[\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\S][\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\s\\S][\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\S][\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\S][\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\S][\\s\\x00\\x01\\xff\\xfe])([\\x00\\s\\S]{2})");
        private static readonly Regex rgx_accessories = new("(?s)(\\x64\\x00\\x00\\x00)([\\s\\S])([\\s\\S])([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)(\\x00{0,4}(\\x64\\x00|[\\s\\S]{2})[\\x00\\s\\S]{0,2})([\\s\\S]{4})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{4})");

        // Main program loop
        static void Main()
        {
            // Run the program until manually closed
            while (true)
            {
                // Display introduction message
                Console.WriteLine("""
                 -------------------------------------
                 Dokapon Kingdom Randomizer by X Kirby
                  v
                """ + RandomVersion + "\n" +
                """
                 -------------------------------------
                """);

                // Grab the file path of a necessary file
                // If blank, use the program's main folder.
                Console.WriteLine("""
                    Type in the path to your original 
                    """
                    + FileBase +
                    """
                     file. Enter nothing to use the program's folder, or type exit to shut down.> 
                    """);
                string? pth = Console.ReadLine();
                if (pth == null || pth.Trim().ToLower() == "exit") break;
                pth = pth.Trim().Trim('"');
                pth = pth.Length == 0 ? AppContext.BaseDirectory + FileBase : pth;

                // At this point, it should check if the file exists and if it doesn't find it, close the program.
                if (!File.Exists(pth))
                {
                    Console.WriteLine("""
                         Error : Game file not found. Path used: 
                        """ + pth + """
                        .
                        """);
                    break;
                }

                // The October 2025 update moved the data around, so work out which build this file is from.
                int ver = Array.IndexOf(FileSizeByBuild, new FileInfo(pth).Length);
                if (ver < 0)
                {
                    Console.WriteLine("""
                        This file's size matches neither known build of the game.
                        Is it from before the October 2025 update (0) or the current game (1)? Any other value shuts down.> 
                        """);
                    bool vtest = int.TryParse(Console.ReadLine(), out ver);
                    if (!vtest || ver < 0 || ver > 1) break;
                }
                Console.WriteLine(ver == 0 ? "Detected the build from before the October 2025 update." : "Detected the current build.");

                // Ask to make a backup, which is recommended. Just in case.
                Console.WriteLine("""
                    Make a backup of your game file? This might take a while. (0) for no, (1) for yes.> 
                    """);

                // Check backup value, but this time don't break the program, just assume 0.
                string? inp = Console.ReadLine();
                bool inptest = int.TryParse(inp, out int bck);
                if (inp == null || !inptest || bck < 0 || bck > 1) bck = 0;
                if (bck == 1 && !File.Exists(pth + ".backup"))
                {
                    File.Copy(pth, pth + ".backup");
                }

                // Start to Setup the Randomizer
                SetupRandomizer(ver, pth);
            }
        }

        // Setup Randomizer function
        static void SetupRandomizer(int version, string filePath)
        {
            // Load the game data file.
            Console.WriteLine("""
                    Loading game file as byte array into memory...
                    """
                    );
            byte[]? fileData = File.ReadAllBytes(filePath);
            Console.WriteLine("Done.");

            // Initialize a bunch of settings variables

            // Equipment
            bool shuffleEquip = false;
            bool shuffleMagic = false;
            bool shuffleItems = false;
            bool shuffleConsumables = false;
            bool shuffleSpecial = false;
            bool randoEquip = false;
            bool randoEquipSerious = false;
            float randoEquipMultiplier = 1.0f;
            float randoEquipVarianceWeapons = 0.0f;
            float randoEquipVarianceShields = 0.0f;
            float randoEquipVarianceAccessories = 0.0f;

            // Magic
            bool randoMagic = false;
            bool randoMagicSerious = false;
            float randoMagicMultiplier = 1.0f;
            float randoMagicVarianceOffense = 0.0f;
            float randoMagicVarianceDefense = 0.0f;
            float randoMagicVarianceField = 0.0f;

            // Player Classes
            bool randoClass = false;
            bool randoClassSerious = false;
            float randoClassMultiplier = 1.0f;
            float randoClassVarianceBase = 0.0f;
            float randoClassVarianceLevelUp = 0.0f;
            float randoClassVarianceSalary = 0.0f;
            float randoClassVarianceCapacity = 0.0f;

            // Monsters
            bool randoMonster = false;
            bool randoMonsterSerious = false;
            float randoMonsterMultiplier = 1.0f;
            float randoMonsterVarianceBase = 0.0f;

            // Prices
            bool randoPrices = false;
            bool randoPricesSerious = false;
            float randoPricesMultiplier = 1.0f;
            float randoPricesVariance = 0.0f;
            int randoPricesMinimum = 2;

            // Other
            bool randoItems = false;
            bool randoShops = false;
            bool randoDrops = false;
            bool randoDropsSerious = false;
            bool randoExploits = false;
            bool randoPrankNames = false;
            bool randoOutputLog = false;
            int randoSeed = 0;

            // Equipment Shuffle Toggle
            Console.WriteLine("""

                Shuffle which Weapons, Shields, and Accessories sit in which slot? Names and abilities move, stats and prices stay put. [true or false]>
                """);
            string? inp = Console.ReadLine();
            bool inptest = bool.TryParse(inp, out bool eqf);
            if (inp == null || !inptest) eqf = false;
            shuffleEquip = eqf;

            // Magic Shuffle Toggle
            Console.WriteLine("""
                
                Shuffle which Offensive, Defensive, and Field Magic sit in which slot? Names and effects move, potency and prices stay put. [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool mgf);
            if (inp == null || !inptest) mgf = false;
            shuffleMagic = mgf;

            // Item Shuffle Toggle
            Console.WriteLine("""
                
                Shuffle which Consumables and Gifts sit in which slot? Names and types move, prices and values stay put. [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool itf);
            if (inp == null || !inptest) itf = false;
            shuffleItems = itf;

            // Consumable Shuffle Toggle
            if (itf)
            {
                Console.WriteLine("""
                
                EXPERIMENTAL: Also shuffle Consumables? The game may pick their effects by ID, so a "6 Crystal" could end up named something else but still move you 6 spaces. Gifts are always shuffled. [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool itc);
                if (inp == null || !inptest) itc = false;
                shuffleConsumables = itc;
            }

            // Check for Shuffle stuff before continuing
            if (eqf || mgf || itf)
            {
                // Should story/unbuyable items be mixed in with everything else?
                Console.WriteLine("""
                
                Include story and unbuyable items (base price of 2 or less) in the shuffles? If false, they stay in their own slots. [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool ssp);
                if (inp == null || !inptest) ssp = false;
                shuffleSpecial = ssp;
            }

            // Equipment Randomizer Toggle
            Console.WriteLine("""

                Allow Randomized Equipment? [true or false]>
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool eqr);
            if (inp == null || !inptest) eqr = false;
            randoEquip = eqr;

            // Check for Equipment Randomizer stuff before continuing
            if (eqr)
            {
                // Do you want to SERIOUSLY Randomize the Equipment?
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Equipment? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool eqs);
                if (inp == null || !inptest) eqs = false;
                randoEquipSerious = eqs;

                // Equipment Strength Multiplier
                Console.WriteLine("""
                
                Equipment Strength Multiplier? [0.05 - 2.00]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float eqm);
                if (inp == null || !inptest) eqm = 1.0f;
                eqm = Math.Clamp(eqm, 0.05f, 2.0f);
                randoEquipMultiplier = eqm;

                // Weapon Stat Variance
                Console.WriteLine("""
                
                Weapon Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float eq1);
                if (inp == null || !inptest) eq1 = 0.0f;
                eq1 = Math.Clamp(eq1, 0.0f, 1.0f);
                randoEquipVarianceWeapons = eq1;

                // Shield Stat Variance
                Console.WriteLine("""
                
                Shield Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float eq2);
                if (inp == null || !inptest) eq2 = 0.0f;
                eq2 = Math.Clamp(eq2, 0.0f, 1.0f);
                randoEquipVarianceShields = eq2;

                // Accessory Stat Variance
                Console.WriteLine("""
                
                Accessory Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float eq3);
                if (inp == null || !inptest) eq3 = 0.0f;
                eq3 = Math.Clamp(eq3, 0.0f, 1.0f);
                randoEquipVarianceAccessories = eq3;
            }

            // Magic Randomizer Toggle
            Console.WriteLine("""
                
                Allow Randomized Magic? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool mgr);
            if (inp == null || !inptest) mgr = false;
            randoMagic = mgr;

            // Check for Magic Randomizer stuff before continuing
            if (mgr)
            {
                // Do you want to SERIOUSLY Randomize the Magic?
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Magic? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool mgs);
                if (inp == null || !inptest) mgs = false;
                randoMagicSerious = mgs;

                // Magic Strength Multiplier
                Console.WriteLine("""
                
                Magic Strength Multiplier? [0.05 - 2.00]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mgm);
                if (inp == null || !inptest) mgm = 1.0f;
                mgm = Math.Clamp(mgm, 0.05f, 2.0f);
                randoMagicMultiplier = mgm;

                // Offense Magic Stat Variance
                Console.WriteLine("""
                
                Offense Magic Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mg1);
                if (inp == null || !inptest) mg1 = 0.0f;
                mg1 = Math.Clamp(mg1, 0.0f, 1.0f);
                randoMagicVarianceOffense = mg1;

                // Defense Magic Stat Variance
                Console.WriteLine("""
                
                Defense Magic Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mg2);
                if (inp == null || !inptest) mg2 = 0.0f;
                mg2 = Math.Clamp(mg2, 0.0f, 1.0f);
                randoMagicVarianceDefense = mg2;

                // Field Magic Stat Variance
                Console.WriteLine("""
                
                Field Magic Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mg3);
                if (inp == null || !inptest) mg3 = 0.0f;
                mg3 = Math.Clamp(mg3, 0.0f, 1.0f);
                randoMagicVarianceField = mg3;
            }

            // Player Class Randomizer Toggle
            Console.WriteLine("""
                
                Allow Randomized Player Classes? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool pcr);
            if (inp == null || !inptest) pcr = false;
            randoClass = pcr;

            // Check for Player Class Randomizer stuff before continuing
            if (pcr)
            {
                // Do you want to SERIOUSLY Randomize the Player Classes?
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Player Classes? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool pcs);
                if (inp == null || !inptest) pcs = false;
                randoClassSerious = pcs;

                // Player Class Strength Multiplier
                Console.WriteLine("""
                
                Player Class Strength Multiplier? (NOTE: Does not affect Inventory Capacity) [0.25 - 3.00]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pcm);
                if (inp == null || !inptest) pcm = 1.0f;
                pcm = Math.Clamp(pcm, 0.25f, 3.0f);
                randoClassMultiplier = pcm;

                // Player Class Base Stat Variance
                Console.WriteLine("""
                
                Player Class Base Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pc1);
                if (inp == null || !inptest) pc1 = 0.0f;
                pc1 = Math.Clamp(pc1, 0.0f, 1.0f);
                randoClassVarianceBase = pc1;

                // Player Class LevelUp Stat Variance
                Console.WriteLine("""
                
                Player Class LevelUp Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pc2);
                if (inp == null || !inptest) pc2 = 0.0f;
                pc2 = Math.Clamp(pc2, 0.0f, 1.0f);
                randoClassVarianceLevelUp = pc2;

                // Player Class Salary Variance
                Console.WriteLine("""
                
                Player Class Salary Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pc3);
                if (inp == null || !inptest) pc3 = 0.0f;
                pc3 = Math.Clamp(pc3, 0.0f, 1.0f);
                randoClassVarianceSalary = pc3;

                // Player Class Inventory Capacity Variance
                Console.WriteLine("""
                
                Player Class Inventory Capacity Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pc4);
                if (inp == null || !inptest) pc4 = 0.0f;
                pc4 = Math.Clamp(pc4, 0.0f, 1.0f);
                randoClassVarianceCapacity = pc4;
            }

            // Monster Randomizer Toggle
            Console.WriteLine("""
                
                Allow Randomized Monsters? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool mnr);
            if (inp == null || !inptest) mnr = false;
            randoMonster = mnr;

            // Check for Player Class Randomizer stuff before continuing
            if (mnr)
            {
                // Do you want to SERIOUSLY Randomize the Monsters?
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Monsters? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool mns);
                if (inp == null || !inptest) mns = false;
                randoMonsterSerious = mns;

                // Monster Strength Multiplier
                Console.WriteLine("""
                
                Monster Strength Multiplier? [0.25 - 3.00]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mnm);
                if (inp == null || !inptest) mnm = 1.0f;
                mnm = Math.Clamp(mnm, 0.25f, 3.0f);
                randoMonsterMultiplier = mnm;

                // Monster Base Stat Variance
                Console.WriteLine("""
                
                Monster Base Stat Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float mn1);
                if (inp == null || !inptest) mn1 = 0.0f;
                mn1 = Math.Clamp(mn1, 0.0f, 1.0f);
                randoMonsterVarianceBase = mn1;
            }

            // Price Randomizer Toggle
            Console.WriteLine("""
                
                Allow Randomized Prices? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool prr);
            if (inp == null || !inptest) prr = false;
            randoPrices = prr;

            // Check for Price Randomizer stuff before continuing
            if (prr)
            {
                // Do you want to SERIOUSLY Randomize the Prices?
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Prices? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool prs);
                if (inp == null || !inptest) prs = false;
                randoPricesSerious = prs;

                // Price Strength Multiplier
                Console.WriteLine("""
                
                Price Strength Multiplier? [0.25 - 3.00]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float prm);
                if (inp == null || !inptest) prm = 1.0f;
                prm = Math.Clamp(prm, 0.25f, 3.0f);
                randoPricesMultiplier = prm;

                // Price Variance
                Console.WriteLine("""
                
                Price Variance? [0.0 - 1.0]> 
                """);
                inp = Console.ReadLine();
                inptest = float.TryParse(inp, out float pr1);
                if (inp == null || !inptest) pr1 = 0.0f;
                pr1 = Math.Clamp(pr1, 0.0f, 1.0f);
                randoPricesVariance = pr1;

                // Price Minimum
                Console.WriteLine("""
                
                Price Minimum? [2 - 1000]> 
                """);
                inp = Console.ReadLine();
                inptest = int.TryParse(inp, out int pr2);
                if (inp == null || !inptest) pr2 = 2;
                pr2 = Math.Clamp(pr2, 2, 1000);
                randoPricesMinimum = pr2;
            }

            // Randomized Items Toggle
            Console.WriteLine("""
                
                Allow Randomized Items? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool ot0);
            if (inp == null || !inptest) ot0 = false;
            randoItems = ot0;

            // Randomized Shops Toggle
            Console.WriteLine("""
                
                Allow Randomized Shops? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool ot1);
            if (inp == null || !inptest) ot1 = false;
            randoShops = ot1;

            // Randomized Drops Toggles
            Console.WriteLine("""
                
                Allow Randomized Drops? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool ot4);
            if (inp == null || !inptest) ot4 = false;
            randoDrops = ot4;

            if (ot4)
            {
                Console.WriteLine("""
                
                Allow SERIOUSLY Randomized Drops? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool ot5);
                if (inp == null || !inptest) ot5 = false;
                randoDropsSerious = ot5;
            }

            // Allow Exploitable Items Toggle
            Console.WriteLine("""
                
                Allow Exploitabls? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool ot6);
            if (inp == null || !inptest) ot6 = false;
            randoExploits = ot6;

            // Allow Prank Names Toggle
            {
                Console.WriteLine("""
                
                Randomize Prank Names? [true or false]> 
                """);
                inp = Console.ReadLine();
                inptest = bool.TryParse(inp, out bool ot7);
                if (inp == null || !inptest) ot7 = false;
                randoPrankNames = ot7;
            }

            // Type in a number for the randomization seed
            Console.WriteLine("""
                
                Input a seed [0 - 999999999]> 
                """);
            inp = Console.ReadLine();
            inptest = int.TryParse(inp, out int ot8);
            if (inp == null || !inptest) ot8 = Math.Clamp(new Random(DateTime.MaxValue.Second).Next(0, 999999999), 0, 999999999);
            randoSeed = Math.Clamp(ot8, 0, 999999999);

            // Write Detailed Output Log Toggle
            Console.WriteLine("""
                
                Write Detailed Output Log? [true or false]> 
                """);
            inp = Console.ReadLine();
            inptest = bool.TryParse(inp, out bool ot9);
            if (inp == null || !inptest) ot9 = false;
            randoOutputLog = ot9;

            // Write basic Output Log information
            Console.WriteLine("Writing basic Output Log information...");
            StreamWriter outputLog = File.CreateText(filePath + "_" + randoSeed + ".txt");
            using (outputLog)
            {
                outputLog.WriteLine("#########################################");
                outputLog.WriteLine(" DOKAPON KINGDOM RANDOMIZER");
                outputLog.WriteLine(" Seed: " + randoSeed);
                outputLog.WriteLine("#########################################");
                outputLog.WriteLine(" Shuffled Equipment: " + shuffleEquip);
                outputLog.WriteLine(" Shuffled Magic: " + shuffleMagic);
                outputLog.WriteLine(" Shuffled Items: " + shuffleItems);
                outputLog.WriteLine(" Shuffled Consumables: " + shuffleConsumables);
                outputLog.WriteLine(" Shuffles Include Story Items: " + shuffleSpecial);
                outputLog.WriteLine(" Randomized Equipment: " + randoEquip);
                outputLog.WriteLine(" Randomized Magic: " + randoMagic);
                outputLog.WriteLine(" Randomized Items: " + randoItems);
                outputLog.WriteLine(" Randomized Player Classes: " + randoClass);
                outputLog.WriteLine(" Randomized Monsters: " + randoMonster);
                outputLog.WriteLine(" Randomized Shops: " + randoShops);
                outputLog.WriteLine(" Randomized Drops: " + randoDrops);
                outputLog.WriteLine(" Allow Exploitables: " + randoExploits);
                outputLog.WriteLine(" Randomized Prank Names: " + randoPrankNames);
                outputLog.WriteLine(" Randomized Prices: " + randoPrices);
                outputLog.WriteLine("#########################################");
                outputLog.WriteLine(" Seriously Randomized Equipment: " + randoEquipSerious);
                outputLog.WriteLine(" Seriously Randomized Magic: " + randoMagicSerious);
                outputLog.WriteLine(" Seriously Randomized Player Classes: " + randoClassSerious);
                outputLog.WriteLine(" Seriously Randomized Monsters: " + randoMonsterSerious);
                outputLog.WriteLine(" Seriously Randomized Drops: " + randoDropsSerious);
                outputLog.WriteLine(" Seriously Randomized Prices: " + randoPricesSerious);
                outputLog.WriteLine("#########################################\n");

                // Equipment Settings
                if (randoEquip)
                {
                    outputLog.WriteLine("-- EQUIPMENT SETTINGS --");
                    outputLog.WriteLine("Equipment Stat Multiplier: " + randoEquipMultiplier);
                    outputLog.WriteLine("Weapon Stat Variance: " + randoEquipVarianceWeapons);
                    outputLog.WriteLine("Shields Stat Variance: " + randoEquipVarianceShields);
                    outputLog.WriteLine("Accessories Stat Variance: " + randoEquipVarianceAccessories);
                }

                // Magic Settings
                if (randoMagic)
                {
                    outputLog.WriteLine("-- MAGIC SETTINGS --");
                    outputLog.WriteLine("Magic Stat Multiplier: " + randoMagicMultiplier);
                    outputLog.WriteLine("Offense Magic Stat Variance: " + randoMagicVarianceOffense);
                    outputLog.WriteLine("Defense Magic Stat Variance: " + randoMagicVarianceDefense);
                    outputLog.WriteLine("Field Magic Stat Variance: " + randoMagicVarianceField);
                }

                // Player Class Settings
                if (randoClass)
                {
                    outputLog.WriteLine("-- PLAYER CLASS SETTINGS --");
                    outputLog.WriteLine("Player Class Stat Multiplier: " + randoClassMultiplier);
                    outputLog.WriteLine("Player Class Base Stat Variance: " + randoClassVarianceBase);
                    outputLog.WriteLine("Player Class LevelUp Stat Variance: " + randoClassVarianceLevelUp);
                    outputLog.WriteLine("Player Class Salary Variance: " + randoClassVarianceSalary);
                    outputLog.WriteLine("Player Class Inventory Capacity Variance: " + randoClassVarianceCapacity);
                }

                // Monster Settings
                if (randoMonster)
                {
                    outputLog.WriteLine("-- MONSTER SETTINGS --");
                    outputLog.WriteLine("Monster Base Stat Multiplier: " + randoMonsterMultiplier);
                    outputLog.WriteLine("Monster Base Stat Variance: " + randoMonsterVarianceBase);
                }

                // Price Settings
                if (randoPrices)
                {
                    outputLog.WriteLine("-- PRICE SETTINGS --");
                    outputLog.WriteLine("Price Multiplier: " + randoPricesMultiplier);
                    outputLog.WriteLine("Price Variance: " + randoPricesVariance);
                    outputLog.WriteLine("Price Minimum: " + randoPricesMinimum);
                }
            }

            // Mention that it's done.
            Console.WriteLine("Done.");

            // Actual Randomizer Functions
            fileData = shuffleItems ? ShuffleItems(version, filePath, fileData, settings: new List<object>() { randoSeed, randoOutputLog, shuffleSpecial, shuffleConsumables }) : fileData;
            fileData = randoItems ? RandomizeItems(version, filePath, fileData, settings: new List<object>() { randoSeed, randoPrices, randoPricesSerious, randoPricesVariance, randoPricesMinimum, randoExploits, randoOutputLog }) : fileData;
            fileData = shuffleEquip ? ShuffleEquip(version, filePath, fileData, settings: new List<object>() { randoSeed, randoOutputLog, shuffleSpecial }) : fileData;
            fileData = randoEquip ? RandomizeEquip(version, filePath, fileData, settings: new List<object>() { randoSeed, randoPrices, randoPricesSerious, randoPricesVariance, randoPricesMinimum, randoEquipSerious, randoEquipMultiplier, randoEquipVarianceWeapons, randoEquipVarianceShields, randoEquipVarianceAccessories, randoOutputLog }) : fileData;
            fileData = shuffleMagic ? ShuffleMagic(version, filePath, fileData, settings: new List<object>() { randoSeed, randoOutputLog, shuffleSpecial }) : fileData;
            fileData = randoMagic ? RandomizeMagic(version, filePath, fileData, settings: new List<object>() { randoSeed, randoPrices, randoPricesSerious, randoPricesVariance, randoPricesMinimum, randoMagicSerious, randoMagicMultiplier, randoMagicVarianceOffense, randoMagicVarianceDefense, randoMagicVarianceField, randoOutputLog }) : fileData;
            fileData = randoClass ? RandomizeClasses(version, filePath, fileData, settings: new List<object>() { randoSeed, randoClassSerious, randoClassMultiplier, randoClassVarianceBase, randoClassVarianceLevelUp, randoClassVarianceSalary, randoClassVarianceCapacity, randoOutputLog }) : fileData;
            fileData = randoMonster ? RandomizeMonsters(version, filePath, fileData, settings: new List<object>() { randoSeed, randoMonsterSerious, randoMonsterMultiplier, randoMonsterVarianceBase, randoOutputLog }) : fileData;
            fileData = randoShops ? RandomizeShops(version, filePath, fileData, settings: new List<object>() { randoSeed, randoExploits, randoOutputLog }) : fileData;
            fileData = randoDrops ? RandomizeDrops(version, filePath, fileData, settings: new List<object>() { randoSeed, randoExploits, randoOutputLog }) : fileData;
            fileData = randoPrankNames ? RandomizePrankNames(version, filePath, fileData, settings: new List<object>() { randoSeed, randoOutputLog }) : fileData;

            // Save the file data
            Console.WriteLine("Saving data to " + filePath + "...");
            File.WriteAllBytes(filePath, fileData);

            // Tell the user they're done.
            Console.WriteLine("Done.");
            return;
        }

        // Get Random Item function
        public static byte GetRandomItem(Random RNG, int randoSeed, byte tableID)
        {
            byte ID = 0;
            switch(tableID)
            {
                // Weapons
                case 1:
                    ID = (byte)RNG.Next(1, 0x43);
                    break;
                //Shields
                case 2:
                    ID = (byte)RNG.Next(1, 0x28);
                    break;
                // Accessories
                case 3:
                    ID = (byte)RNG.Next(1, 0x21);
                    break;
                // Consumables
                case 5:
                    List<byte> consumableTable = new List<byte>() { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xa, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2e, 0x2f, 0x30, 0x31, 0x38 };
                    ID = consumableTable[RNG.Next(0, consumableTable.Count-1)];
                    consumableTable.Clear();
                    break;
                // Attack Magic
                case 6:
                    ID = (byte)RNG.Next(1, 0x17);
                    break;
                // Defense Magic
                case 7:
                    ID = (byte)RNG.Next(1, 0x13);
                    break;
                // Field Magic
                case 8:
                    ID = (byte)RNG.Next(1, 0x26);
                    break;
                // Gain Money Effect
                case 0x80:
                    ID = (byte)RNG.Next(0, 0x13);
                    break;
                // Lose HP Effect
                case 0x81:
                    ID = (byte)RNG.Next(0, 6);
                    break;
                // Gain Status Effect
                case 0x82:
                    ID = (byte)RNG.Next(0, 9);
                    break;
                // Random Warp and Bankrupt Effects
                case 0x83:
                case 0x84:
                    break;
                // Lose Consumables Effect
                case 0x85:
                    ID = (byte)RNG.Next(0, 2);
                    break;
                // Lose Field Magic Items Effect
                case 0x86:
                    ID = (byte)RNG.Next(0, 2);
                    break;
                // Lose Money Effect
                case 0x87:
                    ID = (byte)RNG.Next(0, 8);
                    break;
            }
            return ID;
        }

        // Prank Names Randomizer function
        public static byte[] RandomizePrankNames(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 2)
            {
                Console.WriteLine("Error: RandomizeDrops() -> settings doesn't have 2 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Prank Names...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_pranknames = new("(?s)(\\xBF\\x00\\x00\\x00)([\\x00-\\xFF]{4})([\\x01-\\xFF]{4,12}?\\x00{1,4}?)");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Grab Prank Names file contents
            string[] PrankNames = File.ReadAllLines(AppContext.BaseDirectory + "pranknames.txt");

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[1]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == PRANK NAMES TABLE == "); outputLog.Close(); } }

            MatchCollection pranknames = rgx_pranknames.Matches(fileString, LocPrankNames[version]);

            foreach (Match s in pranknames)
            {
                // Split the groups found using Regex
                GroupCollection g = s.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocPrankNames[version] + 0x7E8) { break; }

                string oldName = g[3].Value;
                string newName = "";
                int searches = 0;
                do
                {
                    searches++;
                    newName = PrankNames[RNG.Next(PrankNames.Length - 1)];
                    if (newName.Length < oldName.Length)
                    { break; }
                    if (searches == 100)
                    { newName = oldName; }
                }
                while (searches < 100);

                // Substring Replacement Loop
                for (int i = 0; i < g[3].Length; i += 1)
                {
                    char c;
                    if (i < newName.Length)
                    { c = newName[i]; }
                    else { c = ((byte)0x00).ToString().ToCharArray()[0]; }

                    fileData[g[3].Index + i] = (byte)c;
                }

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[1]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Prank Name Changes: " + oldName + " -> " + newName); outputLog.Close(); } }
            }

            fileString = "";
            return fileData;
        }

        // Drop Randomizer function
        public static byte[] RandomizeDrops(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 3)
            {
                Console.WriteLine("Error: RandomizeDrops() -> settings doesn't have 3 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Drops...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_dropsspaces = new("(?s)([\\x04-\\x42])\\x00([\\x06\\x08\\x0A])\\x00(([\\s\\S][\\x01-\\x08\\x80-\\x87])+)");
            Regex rgx_dropsmonsters = new("(?s)(\\x53\\x00\\x00\\x00)([\\x00-\\x88])([\\x00-\\x64]{2})\\x00([\\s\\S]{4})");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == BOARD SPACE DROPS TABLE == "); outputLog.Close(); } }

            // Space Drop Tables
            List<byte> exSpaceDropTableIDs = new List<byte>() { 1, 2, 3, 5, 6, 7, 8, 0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87 };
            MatchCollection spacedrops = rgx_dropsspaces.Matches(fileString, LocDropsSpaces[version]);
            foreach (Match s in spacedrops)
            {
                // Split the groups found using Regex
                GroupCollection g = s.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocDropsSpaces[version] + 0x134C) { break; }

                // Subtable Searches
                for (int i = 0; i < g[3].Length; i+=2)
                {
                    // Store Old Item ID and its Table ID.
                    byte oldItemID = (byte)(fileData[g[3].Index + i]);
                    byte oldItemTableID = (byte)(fileData[g[3].Index + i + 1]);

                    // Store New Item ID and its Table ID. Use old Table ID if "Exploits" aren't enabled.
                    byte newItemTableID = oldItemTableID;
                    if ((bool)settings[1])
                        { newItemTableID = exSpaceDropTableIDs[RNG.Next(0, exSpaceDropTableIDs.Count-1)]; }
                    byte newItemID = GetRandomItem(RNG, (int)settings[0], newItemTableID);
                    
                    // Write Data to File
                    fileData[g[3].Index + i] = newItemID;
                    fileData[g[3].Index + i + 1] = newItemTableID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Loot Space Drop Item ID Changes: " + oldItemID + ", " + oldItemTableID + " -> " + newItemID + ", " + newItemTableID); outputLog.Close(); } }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == MONSTER DROPS TABLE == "); outputLog.Close(); } }

            // Monster Drop Tables
            List<byte> exMonsterDropTableIDs = new List<byte>() { 1, 2, 3, 5, 6, 7, 8 };
            MatchCollection monsterdrops = rgx_dropsmonsters.Matches(fileString, LocDropsMonsters[version]);
            foreach (Match s in monsterdrops)
            {
                // Split the groups found using Regex
                GroupCollection g = s.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocDropsMonsters[version] + 0x66C) { break; }

                // Store Monster ID
                byte monsterID = fileData[g[2].Index];

                // Drop Chances
                byte[] dropChances = new byte[2] { fileData[g[3].Index], fileData[g[3].Index + 1] };
                byte[] newChances = new byte[2] { dropChances[0] == 0 ? (byte)0 : (byte)RNG.Next(1, 100), dropChances[1] == 0 ? (byte)0 : (byte)RNG.Next(1, 100) };

                // Subtables Search
                for (int i = 0; i < g[4].Length; i += 2)
                {
                    // Store Old Item ID and its Table ID.
                    byte oldItemID = fileData[g[4].Index + i];
                    byte oldItemTableID = fileData[g[4].Index + i + 1];

                    // Store New Item ID and its Table ID. Use old Table ID if "Exploits" aren't enabled.
                    byte newItemTableID = oldItemTableID;
                    if ((bool)settings[1])
                        { newItemTableID = exMonsterDropTableIDs[RNG.Next(0, exMonsterDropTableIDs.Count - 1)]; }
                    byte newItemID = GetRandomItem(RNG, (int)settings[0], newItemTableID);

                    // Check if Table is Valid
                    if ((newItemTableID > 0 && newItemTableID < 9) || (newItemTableID > 0x7F && newItemTableID < 0x88))
                    {
                        // Royal Ring Fix
                        if (oldItemID == 0x37 && oldItemTableID == 0x05)
                        {
                            newChances[i / 2] = (byte)100;
                            newItemID = 0x37;
                            newItemTableID = 0x05;
                        }

                        // Write Dropped Items to File
                        fileData[g[4].Index + i] = newItemID;
                        fileData[g[4].Index + i + 1] = newItemTableID;

                        // Write Drop Chances to File
                        fileData[g[3].Index + i] = newChances[0];
                        fileData[g[3].Index + i + 1] = newChances[1];
                    }

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2])
                    {
                        using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                        {
                            outputLog.WriteLine("Monster Drop Item ID Changes: " + oldItemID + ", " + oldItemTableID + " -> " + newItemID + ", " + newItemTableID);
                            outputLog.WriteLine("Drop Chance Changes: " + dropChances[0] + ", " + dropChances[1] + " -> " + newChances[0] + ", " + newChances[1]);
                            outputLog.WriteLine("");
                            outputLog.Close();
                        }
                    }
                }
            }

            // Tell the user it's done randomizing shops.
            Console.WriteLine("Done.");

            exMonsterDropTableIDs.Clear();
            exSpaceDropTableIDs.Clear();
            fileString = "";
            return fileData;
        }

        // Item Randomizer function
        public static byte[] RandomizeItems(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 7)
            {
                Console.WriteLine("Error: RandomizeItems() -> settings doesn't have 7 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Items...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_consumables = new("(?s)(\\x69\\x00{3})([\\x01-\\x46])([\\x00\\s\\S])([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)(\\x00{1,8})([\\x01-\\xff][\\x00-\\xff]{3})([\\s\\S]{2})([\\s\\S]{2})");
            Regex rgx_gifts = new("(?s)(\\x6c\\x00{3})([\\x47-\\x9d])(\\x00)([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)(\\x00{1,8})([\\x01-\\xff][\\x00-\\xff]{3})([\\s\\S]{4})([\\s\\S]{4})");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[6]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == ITEMS TABLE == "); outputLog.Close(); } }

            // Consumables
            MatchCollection consumables = rgx_consumables.Matches(fileString, LocStatsConsumables[version]);
            foreach (Match c in consumables)
            {
                // Split the groups found using Regex
                GroupCollection g = c.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsConsumables[version] + 0x7DC) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                byte item_type = fileData[g[3].Index];
                string item_name = g[5].Value;
                int[] price = new int[2] { fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8) + (fileData[g[7].Index + 2] << 16) + (fileData[g[7].Index + 3] << 24), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Write Data to File
                fileData[g[7].Index] = (byte)(price[1] % 0x100);
                fileData[g[7].Index + 1] = (byte)((price[1] >> 8) % 0x100);
                fileData[g[7].Index + 2] = (byte)((price[1] >> 16) % 0x100);
                fileData[g[7].Index + 3] = (byte)((price[1] >> 24) % 0x100);

                if ((bool)settings[6])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Consumable ID #: " + item_id);
                        outputLog.WriteLine("Consumable Type #: " + item_type);
                        outputLog.WriteLine("Consumable Name: " + item_name);
                        outputLog.WriteLine("Consumable Price: " + price[0] + " -> " + price[1]);
                        outputLog.Close();
                    }
                }
            }

            // Tell the user it's done randomizing shops.
            Console.WriteLine("Done.");

            fileString = "";
            return fileData;
        }

        // Shop Randomizer function
        public static byte[] RandomizeShops(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 3)
            {
                Console.WriteLine("Error: RandomizeShops() -> settings doesn't have 3 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Shops...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_equipshop = new("(?s)([\\x01-\\x43]{1,10})\\x00([\\x01-\\x28]{1,10})\\x00");
            Regex rgx_itemshop = new("(?s)([\\x01-\\x31]{8,9}?)\\x00");
            Regex rgx_magicshop = new("(?s)([\\x38-\\]]{8})\\x00([\\x01-\\x17]{4})\\x00([\\x1f-\\x30]{4})\\x00");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == EQUIPMENT SHOPS TABLE == "); outputLog.Close(); } }

            // Equipment Regex Search
            List<byte> normalWeaponIDs = new List<byte>() { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xa, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x24, 0x26, 0x27, 0x28, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32, 0x33, 0x34, 0x36, 0x39, 0x3c };
            List<byte> normalShieldIDs = new List<byte>() { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xa, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x21, 0x22, 0x23, 0x24, 0x25 };
            MatchCollection equips = rgx_equipshop.Matches(fileString, LocShopEquipment[version]);
            foreach (Match e in equips)
            {
                // Split the groups found using Regex
                GroupCollection g = e.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocShopEquipment[version] + 0x70) { break; }

                // Weapons
                for (int i = 0; i < g[1].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[1].Index + i];
                    byte newID = 1;

                    // If "Exploits" are enabled. Store New Item ID from here.
                    if ((bool)settings[1])
                    { newID = (byte)RNG.Next(1, 67); }
                    else
                    {
                        newID = normalWeaponIDs[RNG.Next(0, normalWeaponIDs.Count-1)];
                    }
                    fileData[g[1].Index + i] = newID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Equipment Shop Weapon ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }

                if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }

                // Shields
                for (int i = 0; i < g[2].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[2].Index + i];
                    byte newID = 1;

                    // If "Exploits" are enabled. Store New Item ID from here.
                    if ((bool)settings[1])
                    { newID = (byte)RNG.Next(1, 40); }
                    else
                    {
                        newID = normalShieldIDs[RNG.Next(0, normalShieldIDs.Count-1)];
                    }
                    fileData[g[2].Index + i] = newID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Equipment Shop Shield ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }

                if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }
            }

            // Consumable Regex Search
            int fixCount = 0;
            List<byte> chapter3Fix = new List<byte>() { 0x8, 0x14, 0x1C, 0x1E, 0x20, 0x24, 0x27, 0x28 };
            List<byte> exConsumableIDs = new List<byte>() { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xa, 0xb, 0xc, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2e, 0x2f, 0x30, 0x31, 0x38 };
            List<byte> normalConsumableIDs = new List<byte>() { 1, 2, 3, 4, 5, 6, 7, 8, 9, 0xa, 0xb, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2e };
            MatchCollection items = rgx_itemshop.Matches(fileString, LocShopConsumables[version]);
            foreach (Match m in items)
            {
                // Split the groups found using Regex
                GroupCollection g = m.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocShopConsumables[version] + 0x76) { break; }

                fixCount++;
                for (int i = 0; i < g[1].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[1].Index + i];
                    byte newID = 1;

                    // Fix for Chapter 3
                    if ((fixCount <= 6 && i == 0) || (fixCount >= 5 && fixCount <= 6 && i == 1))
                    {
                        int findFix = RNG.Next(0, chapter3Fix.Count-1);
                        newID = chapter3Fix[findFix];
                        chapter3Fix.RemoveAt(findFix);
                    }
                    // If "Exploits" are enabled. Store New Item ID from here.
                    else if ((bool)settings[1])
                        { newID = exConsumableIDs[RNG.Next(0, exConsumableIDs.Count-1)]; }
                    else { newID = normalConsumableIDs[RNG.Next(0, normalConsumableIDs.Count-1)]; }
                    fileData[g[1].Index + i] = newID;
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Item Shop Consumable ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }
            }

            if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }

            // Magic Regex Search
            MatchCollection magics = rgx_magicshop.Matches(fileString, LocShopMagic[version]);
            foreach (Match m in magics)
            {
                // Split the groups found using Regex
                GroupCollection g = m.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocShopEquipment[version] + 0xBE) { break; }

                // Field Magic
                for (int i = 0; i < g[1].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[1].Index + i];
                    byte newID = (byte)RNG.Next(0x38, 0x5D);
                    fileData[g[1].Index + i] = newID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Magic Shop Field Magic ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }

                if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }

                // Attack Magic
                for (int i = 0; i < g[2].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[2].Index + i];
                    byte newID = newID = (byte)RNG.Next(1, 0x17);
                    fileData[g[2].Index + i] = newID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Magic Shop Attack Magic ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }

                if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }

                // Defense Magic
                for (int i = 0; i < g[3].Length; i++)
                {
                    // Store Old Item ID
                    byte oldID = fileData[g[3].Index + i];
                    byte newID = (byte)RNG.Next(0x1F, 0x30);
                    fileData[g[3].Index + i] = newID;

                    // Write to Output Log in Detail, if enabled
                    if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("Magic Shop Defense Magic ID Change: " + oldID + " -> " + newID); outputLog.Close(); } }
                }

                if ((bool)settings[2]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine(""); outputLog.Close(); } }
            }

            // Tell the user it's done randomizing shops.
            Console.WriteLine("Done.");

            normalConsumableIDs.Clear();
            normalWeaponIDs.Clear();
            normalShieldIDs.Clear();
            exConsumableIDs.Clear();
            fileString = "";
            return fileData;
        }

        // Monster Randomizer function
        public static byte[] RandomizeMonsters(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 5)
            {
                Console.WriteLine("Error: RandomizeMonsters() -> settings doesn't have 5 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Monsters...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_monsters = new("(?s)(\\x50\\x00{3})([\\x00-\\x88])([\\x00-\\xff])([\\x00-\\xff])\\x00([0-9A-Za-z\\+\\'\\x20\\-]+)\\x00(\\x00{0,3})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})(\\x00\\x00[\\s\\S]{4})([\\s\\S]{2})([\\s\\S]{2})");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[4]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == MONSTER TABLE == "); outputLog.Close(); } }

            // Weapon Regex Search
            MatchCollection monsters = rgx_monsters.Matches(fileString, LocStatsMonsters[version]);
            foreach (Match m in monsters)
            {
                // Split the groups found using Regex
                GroupCollection g = m.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsMonsters[version] + 0x144C) { break; }

                // Pull out the values from each relevant group
                byte monster_id = fileData[g[2].Index];
                string name = g[5].Value;
                short[] hp = new short[2] { (short)(fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8)), 0 };
                short[] atk = new short[2] { (short)(fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[9].Index] + (fileData[g[9].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[10].Index] + (fileData[g[10].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[11].Index] + (fileData[g[11].Index + 1] << 8)), 0 };
                short[] xp = new short[2] { (short)(fileData[g[13].Index] + (fileData[g[13].Index + 1] << 8)), 0 };
                short[] gold = new short[2] { (short)(fileData[g[14].Index] + (fileData[g[14].Index + 1] << 8)), 0 };
                if (monster_id >= 121)
                { continue; }

                // Make sure the default stats are set
                hp[1] = hp[0];
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];
                xp[1] = xp[0];
                gold[1] = gold[0];
                // Are Monster stats seriously randomized?
                if ((bool)settings[1])
                {
                    hp[1] = (short)RNG.Next(10, 5000);
                    atk[1] = (short)RNG.Next(1, 500);
                    def[1] = (short)RNG.Next(1, 500);
                    mag[1] = (short)RNG.Next(1, 500);
                    spd[1] = (short)RNG.Next(1, 500);
                    xp[1] = (short)RNG.Next(1, 15000);
                    gold[1] = (short)RNG.Next(-15000, 15000);
                }

                // Multiply and Clamp the Monster stats
                hp[1] = (short)Math.Clamp((int)((float)hp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 9999);
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 999);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 999);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 999);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 999);
                xp[1] = (short)Math.Clamp((int)((float)xp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 30000);
                gold[1] = (short)Math.Clamp((int)((float)gold[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), -30000, 30000);

                // Write data to file

                // Health
                fileData[g[7].Index] = (byte)((hp[1]) % (0x100));
                fileData[g[7].Index + 1] = (byte)((hp[1] >> 8) % (0x100));

                // Attack
                fileData[g[8].Index] = (byte)((atk[1]) % (0x100));
                fileData[g[8].Index + 1] = (byte)((atk[1] >> 8) % (0x100));

                // Defense
                fileData[g[9].Index] = (byte)((def[1]) % (0x100));
                fileData[g[9].Index + 1] = (byte)((def[1] >> 8) % (0x100));

                // Magic
                fileData[g[10].Index] = (byte)((mag[1]) % (0x100));
                fileData[g[10].Index + 1] = (byte)((mag[1] >> 8) % (0x100));

                // Speed
                fileData[g[11].Index] = (byte)((spd[1]) % (0x100));
                fileData[g[11].Index + 1] = (byte)((spd[1] >> 8) % (0x100));

                // Experience
                fileData[g[13].Index] = (byte)((xp[1]) % (0x100));
                fileData[g[13].Index + 1] = (byte)((xp[1] >> 8) % (0x100));

                // Gold
                fileData[g[14].Index] = (byte)((gold[1]) % (0x100));
                fileData[g[14].Index + 1] = (byte)((gold[1] >> 8) % (0x100));

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[4])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Monster ID #: " + monster_id);
                        outputLog.WriteLine("Monster Name: " + name);
                        outputLog.WriteLine("Monster XP: " + xp[0] + " -> " + xp[1]);
                        outputLog.WriteLine("Monster Gold: " + gold[0] + "G -> " + gold[1] + "G");
                        outputLog.WriteLine("Monster Health: " + hp[0] + " -> " + hp[1]);
                        outputLog.WriteLine("Monster Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Monster Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Monster Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Monster Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Tell the user it's done randomizing monsters.
            Console.WriteLine("Done.");

            fileString = "";
            return fileData;
        }

        // Equipment Randomizer function
        public static byte[] RandomizeEquip(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 11)
            {
                Console.WriteLine("Error: RandomizeEquip() -> settings doesn't have 11 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Equipment...");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[10]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == WEAPON TABLE == "); outputLog.Close(); } }

            // Weapon Regex Search
            MatchCollection weapons = rgx_weapons.Matches(fileString, LocStatsWeapons[version]);
            foreach (Match w in weapons)
            {
                // Split the groups found using Regex
                GroupCollection g = w.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsWeapons[version] + 0xAB4) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[5].Value;
                int[] price = new int[2] { fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8) + (fileData[g[8].Index + 2] << 16) + (fileData[g[8].Index + 3] << 24), 0 };
                short[] atk = new short[2] { (short)(fileData[g[9].Index] + (fileData[g[9].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[10].Index] + (fileData[g[10].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[11].Index] + (fileData[g[11].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[12].Index] + (fileData[g[12].Index + 1] << 8)), 0 };
                short[] hp = new short[2] { (short)(fileData[g[13].Index] + (fileData[g[13].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];
                hp[1] = hp[0];
                // Are Weapon stats seriously randomized?
                if ((bool)settings[5])
                {
                    atk[1] = (short)RNG.Next(1, 100);
                    def[1] = (short)RNG.Next(-100, 100);
                    mag[1] = (short)RNG.Next(-100, 100);
                    spd[1] = (short)RNG.Next(-100, 100);
                    hp[1] = (short)RNG.Next(-100, 100);
                }

                // Multiply and Clamp the Weapon stats
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), 1, 333);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), -333, 333);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), -333, 333);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), -333, 333);
                hp[1] = (short)Math.Clamp((int)((float)hp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), -333, 333);

                // Write data to file

                // Price
                fileData[g[8].Index] = (byte)((price[1]) % (0x100));
                fileData[g[8].Index + 1] = (byte)((price[1] >> 8) % (0x100));
                fileData[g[8].Index + 2] = (byte)((price[1] >> 16) % (0x100));
                fileData[g[8].Index + 3] = (byte)((price[1] >> 24) % (0x100));

                // Attack
                fileData[g[9].Index] = (byte)((atk[1]) % (0x100));
                fileData[g[9].Index + 1] = (byte)((atk[1] >> 8) % (0x100));

                // Defense
                fileData[g[10].Index] = (byte)((def[1]) % (0x100));
                fileData[g[10].Index + 1] = (byte)((def[1] >> 8) % (0x100));

                // Magic
                fileData[g[11].Index] = (byte)((mag[1]) % (0x100));
                fileData[g[11].Index + 1] = (byte)((mag[1] >> 8) % (0x100));

                // Speed
                fileData[g[12].Index] = (byte)((spd[1]) % (0x100));
                fileData[g[12].Index + 1] = (byte)((spd[1] >> 8) % (0x100));

                // Health
                fileData[g[13].Index] = (byte)((hp[1]) % (0x100));
                fileData[g[13].Index + 1] = (byte)((hp[1] >> 8) % (0x100));

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Weapon ID #: " + item_id);
                        outputLog.WriteLine("Weapon Name: " + name);
                        outputLog.WriteLine("Weapon Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Weapon Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Weapon Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Weapon Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Weapon Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("Weapon Health: " + hp[0] + " -> " + hp[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[10]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == SHIELD TABLE == "); outputLog.Close(); } }
            
            // Shield Regex Search
            MatchCollection shields = rgx_shields.Matches(fileString, LocStatsShields[version]);
            foreach (Match s in shields)
            {
                // Split the groups found using Regex
                GroupCollection g = s.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsShields[version] + 0x6AC) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[6].Value.Length > 0 ? g[6].Value : g[7].Value;
                int[] price = new int[2] { fileData[g[10].Index] + (fileData[g[10].Index + 1] << 8) + (fileData[g[10].Index + 2] << 16) + (fileData[g[10].Index + 3] << 24), 0 };
                short[] atk = new short[2] { (short)(fileData[g[12].Index] + (fileData[g[12].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[11].Index] + (fileData[g[11].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[13].Index] + (fileData[g[13].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[14].Index] + (fileData[g[14].Index + 1] << 8)), 0 };
                short[] hp = new short[2] { (short)(fileData[g[15].Index] + (fileData[g[15].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];
                hp[1] = hp[0];
                // Are Shield stats seriously randomized?
                if ((bool)settings[5])
                {
                    atk[1] = (short)RNG.Next(-100, 100);
                    def[1] = (short)RNG.Next(1, 100);
                    mag[1] = (short)RNG.Next(-100, 100);
                    spd[1] = (short)RNG.Next(-100, 100);
                    hp[1] = (short)RNG.Next(-100, 100);
                }

                // Multiply and Clamp the Shield stats
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), -333, 333);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), 1, 333);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), -333, 333);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), -333, 333);
                hp[1] = (short)Math.Clamp((int)((float)hp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), -333, 333);

                // Write data to file

                // Price
                fileData[g[10].Index] = (byte)((price[1]) % (0x100));
                fileData[g[10].Index + 1] = (byte)((price[1] >> 8) % (0x100));
                fileData[g[10].Index + 2] = (byte)((price[1] >> 16) % (0x100));
                fileData[g[10].Index + 3] = (byte)((price[1] >> 24) % (0x100));

                // Attack
                fileData[g[12].Index] = (byte)((atk[1]) % (0x100));
                fileData[g[12].Index + 1] = (byte)((atk[1] >> 8) % (0x100));

                // Defense
                fileData[g[11].Index] = (byte)((def[1]) % (0x100));
                fileData[g[11].Index + 1] = (byte)((def[1] >> 8) % (0x100));

                // Magic
                fileData[g[13].Index] = (byte)((mag[1]) % (0x100));
                fileData[g[13].Index + 1] = (byte)((mag[1] >> 8) % (0x100));

                // Speed
                fileData[g[14].Index] = (byte)((spd[1]) % (0x100));
                fileData[g[14].Index + 1] = (byte)((spd[1] >> 8) % (0x100));

                // Health
                fileData[g[15].Index] = (byte)((hp[1]) % (0x100));
                fileData[g[15].Index + 1] = (byte)((hp[1] >> 8) % (0x100));

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Shield ID #: " + item_id);
                        outputLog.WriteLine("Shield Name: " + name);
                        outputLog.WriteLine("Shield Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Shield Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Shield Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Shield Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Shield Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("Shield Health: " + hp[0] + " -> " + hp[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[10]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == ACCESSORY TABLE == "); outputLog.Close(); } }

            // Accessory Regex Search
            MatchCollection accessories = rgx_accessories.Matches(fileString, LocStatsAccessories[version]);
            foreach (Match a in accessories)
            {
                // Split the groups found using Regex
                GroupCollection g = a.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsAccessories[version] + 0x61A) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[5].Value;
                int[] price = new int[2] { fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8) + (fileData[g[8].Index + 2] << 16) + (fileData[g[8].Index + 3] << 24), 0 };
                short[] atk = new short[2] { (short)(fileData[g[9].Index] + (fileData[g[9].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[10].Index] + (fileData[g[10].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[11].Index] + (fileData[g[11].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[12].Index] + (fileData[g[12].Index + 1] << 8)), 0 };
                short[] hp = new short[2] { (short)(fileData[g[13].Index] + (fileData[g[13].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];
                hp[1] = hp[0];
                // Are Weapon stats seriously randomized?
                if ((bool)settings[5])
                {
                    atk[1] = (short)RNG.Next(-100, 100);
                    def[1] = (short)RNG.Next(-100, 100);
                    mag[1] = (short)RNG.Next(-100, 100);
                    spd[1] = (short)RNG.Next(-100, 100);
                    hp[1] = (short)RNG.Next(-100, 100);
                }

                // Multiply and Clamp the Weapon stats
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), -333, 333);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), -333, 333);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), -333, 333);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), -333, 333);
                hp[1] = (short)Math.Clamp((int)((float)hp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), -333, 333);

                // Write data to file

                // Price
                fileData[g[8].Index] = (byte)((price[1]) % 0x100);
                fileData[g[8].Index + 1] = (byte)((price[1] >> 8) % 0x100);
                fileData[g[8].Index + 2] = (byte)((price[1] >> 16) % 0x100);
                fileData[g[8].Index + 3] = (byte)((price[1] >> 24) % 0x100);

                // Attack
                fileData[g[9].Index] = (byte)((atk[1]) % 0x100);
                fileData[g[9].Index + 1] = (byte)((atk[1] >> 8) % 0x100);

                // Defense
                fileData[g[10].Index] = (byte)((def[1]) % 0x100);
                fileData[g[10].Index + 1] = (byte)((def[1] >> 8) % 0x100);

                // Magic
                fileData[g[11].Index] = (byte)((mag[1]) % 0x100);
                fileData[g[11].Index + 1] = (byte)((mag[1] >> 8) % 0x100);

                // Speed
                fileData[g[12].Index] = (byte)((spd[1]) % 0x100);
                fileData[g[12].Index + 1] = (byte)((spd[1] >> 8) % 0x100);

                // Health
                fileData[g[13].Index] = (byte)((hp[1]) % 0x100);
                fileData[g[13].Index + 1] = (byte)((hp[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Accessory ID #: " + item_id);
                        outputLog.WriteLine("Accessory Name: " + name);
                        outputLog.WriteLine("Accessory Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Accessory Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Accessory Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Accessory Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Accessory Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("Accessory Health: " + hp[0] + " -> " + hp[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Tell the user it's done randomizing equipment.
            Console.WriteLine("Done.");

            fileString = "";
            return fileData;
        }

        // Shuffle Framework
        // Instead of rolling new numbers, deal the game's own data out to different slots.
        // A slot keeps its ID, price, and stats, so every part of the game keeps the power curve it was balanced around.
        // The identity (name, type, special ability data) is what moves between slots.

        // Items at or below this base price are story/unbuyable items (2 is also the lowest price the game uses)
        private const int StoryItemMaxPrice = 2;

        // Describes a table of records for the shuffler. Every record is laid out as:
        //   [marker 4][ID 1] [3 prefix bytes] [name, null-terminated and padded to 4] [tail]
        // PrefixMask and TailMask say what happens to each byte of those parts: 'S' stays with the slot, 'I' moves with the identity.
        // The name always moves. PriceOffset is where the 4 byte price sits in the tail (-1 if there isn't one).
        private record ShuffleTable(string Label, int Start, int Marker, int FirstId, string PrefixMask, string TailMask, int PriceOffset);

        // One record of a table, cut into the pieces the shuffler moves around.
        private record TableRecord(string Name, byte[] Head, byte[] Prefix, byte[] NameField, byte[] Tail);

        // Read a table into records.
        // Returns null if the layout isn't what's expected, so the caller can leave the file alone.
        private static List<TableRecord>? ReadTable(byte[] fileData, ShuffleTable table, out int tableStart, out int tableEnd)
        {
            tableStart = tableEnd = -1;

            // The Loc* offsets are where the older Randomize* regexes start, which is up to ~0x48 bytes after the table's first record
            // (and the gift table's is ~0x80 before it), so look on both sides
            int o = -1;
            for (int s = Math.Max(0, table.Start - 0x100); s < table.Start + 0x100 && s + 8 <= fileData.Length; s++)
            {
                if (BitConverter.ToInt32(fileData, s) == table.Marker && fileData[s + 4] == table.FirstId) { o = s; break; }
            }
            if (o < 0) { return null; }
            tableStart = o;

            // Records keep going for as long as the marker is there and the IDs count up
            List<TableRecord> records = new();
            while (o + 8 <= fileData.Length && BitConverter.ToInt32(fileData, o) == table.Marker && fileData[o + 4] == table.FirstId + records.Count)
            {
                // The name runs to its null terminator, then pads out to a multiple of 4 bytes from the start of the record
                int p = o + 8;
                while (p < fileData.Length && fileData[p] != 0) { p++; }
                if (p >= fileData.Length) { return null; }
                string name = System.Text.Encoding.UTF8.GetString(fileData, o + 8, p - (o + 8));
                p++;
                while ((p - o) % 4 != 0) { p++; }

                int end = p + table.TailMask.Length;
                if (end > fileData.Length) { return null; }

                records.Add(new TableRecord(name, fileData[o..(o + 5)], fileData[(o + 5)..(o + 8)], fileData[(o + 8)..p], fileData[p..end]));
                o = end;
            }

            tableEnd = o;
            return records.Count > 0 ? records : null;
        }

        // Shuffle every table in a list. Each table is its own pool.
        // settings: seed, detailed output log, and whether story/unbuyable items get mixed in too.
        private static byte[] ShuffleTables(string title, ShuffleTable[] tables, int salt, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 3)
            {
                Console.WriteLine("Error: Shuffle" + title + "() -> settings doesn't have 3 values.");
                return fileData;
            }

            Console.WriteLine("Shuffling " + title + "...");

            Random RNG = new((int)settings[0] + salt);

            foreach (ShuffleTable table in tables)
            {
                List<TableRecord>? records = ReadTable(fileData, table, out int tableStart, out int tableEnd);
                if (records == null)
                {
                    Console.WriteLine("Couldn't recognize the " + table.Label.ToLower() + " table layout, skipping it.");
                    continue;
                }

                // Story and unbuyable items have a base price of 2 or less. Unless asked to mix them in, they sit this shuffle out.
                List<int> pool = Enumerable.Range(0, records.Count).Where(i => (bool)settings[2] || table.PriceOffset < 0 || BitConverter.ToInt32(records[i].Tail, table.PriceOffset) > StoryItemMaxPrice).ToList();

                // Fisher-Yates over the pool: slot pool[i] receives the identity that started on slot order[pool[i]]
                int[] order = Enumerable.Range(0, records.Count).ToArray();
                for (int i = pool.Count - 1; i > 0; i--)
                {
                    int j = RNG.Next(i + 1);
                    (order[pool[i]], order[pool[j]]) = (order[pool[j]], order[pool[i]]);
                }

                // Rebuild the table: each slot keeps its own 'S' bytes and takes the 'I' bytes and name from another slot
                List<byte> rebuilt = new();
                for (int i = 0; i < records.Count; i++)
                {
                    TableRecord slot = records[i];
                    TableRecord donor = records[order[i]];
                    rebuilt.AddRange(slot.Head);
                    for (int k = 0; k < slot.Prefix.Length; k++) { rebuilt.Add(table.PrefixMask[k] == 'I' ? donor.Prefix[k] : slot.Prefix[k]); }
                    rebuilt.AddRange(donor.NameField);
                    for (int k = 0; k < slot.Tail.Length; k++) { rebuilt.Add(table.TailMask[k] == 'I' ? donor.Tail[k] : slot.Tail[k]); }
                }

                // Names are different lengths, but they pad to 4 bytes, so a shuffle can't change the table size. Make sure before writing.
                if (rebuilt.Count != tableEnd - tableStart)
                {
                    Console.WriteLine("The shuffled " + table.Label.ToLower() + " table changed size, skipping it.");
                    continue;
                }
                rebuilt.CopyTo(fileData, tableStart);

                // Write to output log, if it exists
                if ((bool)settings[1])
                {
                    using (StreamWriter outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("\n\n == " + table.Label + " SHUFFLE (slot: original -> now) == ");
                        for (int i = 0; i < records.Count; i++)
                        {
                            string price = table.PriceOffset >= 0 ? " (" + BitConverter.ToInt32(records[i].Tail, table.PriceOffset) + "G)" : "";
                            outputLog.WriteLine("ID #" + (table.FirstId + i) + price + ": " + records[i].Name + " -> " + records[order[i]].Name);
                        }
                        outputLog.Close();
                    }
                }
            }

            Console.WriteLine("Done.");

            return fileData;
        }

        // Equipment Shuffler function
        // Weapons, Shields, and Accessories each keep their own pool.
        // Moves: type, name, ability data. Stays: price, stats, sort order.
        public static byte[] ShuffleEquip(int version, string filePath, byte[] fileData, List<object> settings)
        {
            ShuffleTable[] tables = new ShuffleTable[]
            {
                new("WEAPON", LocStatsWeapons[version], 0x58, 1, "SII", "IIII" + new string('S', 16), 4),
                new("SHIELD", LocStatsShields[version], 0x5E, 1, "SII", "IIII" + new string('S', 16), 4),
                new("ACCESSORY", LocStatsAccessories[version], 0x64, 1, "SII", "IIII" + new string('S', 16) + "IIII", 4)
            };
            return ShuffleTables("Equipment", tables, 0, filePath, fileData, settings);
        }

        // Magic Shuffler function
        // Offensive, Defensive, and Field Magic each keep their own pool.
        // Moves: type, name, element/category, animation and effect data. Stays: price, potency, cost.
        public static byte[] ShuffleMagic(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // Tail: price 4, potency 2, category 1, cost 1, animation and effect data 4
            const string magicTail = "SSSSSSISIIII";
            ShuffleTable[] tables = new ShuffleTable[]
            {
                new("OFFENSE MAGIC", LocStatsMagicOffense[version], 0x70, 1, "SII", magicTail, 0),
                new("DEFENSE MAGIC", LocStatsMagicDefense[version], 0x72, 1, "SII", magicTail, 0),
                new("FIELD MAGIC", LocStatsMagicField[version], 0x74, 1, "SII", magicTail, 0)
            };
            return ShuffleTables("Magic", tables, 1, filePath, fileData, settings);
        }

        // Item Shuffler function
        // Gifts always shuffle, and only move names: their price, value to the King, and sort data all stay with the slot.
        // Consumables are opt-in (settings[3]). They move category, type, and name, and keep price and the two shop values after it.
        // Some Consumables are identical apart from their names (the numbered Crystals), so the game may pick their effect by ID.
        // If it does, shuffling them only renames them.
        public static byte[] ShuffleItems(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 4)
            {
                Console.WriteLine("Error: ShuffleItems() -> settings doesn't have 4 values.");
                return fileData;
            }

            List<ShuffleTable> tables = new();
            if ((bool)settings[3]) { tables.Add(new("CONSUMABLE", LocStatsConsumables[version], 0x69, 1, "IIS", new string('S', 8), 0)); }
            tables.Add(new("GIFT", LocStatsGifts[version], 0x6C, 78, "SSS", new string('S', 12), 0));
            return ShuffleTables("Items", tables.ToArray(), 2, filePath, fileData, settings.GetRange(0, 3));
        }
        // Magic Randomizer function
        public static byte[] RandomizeMagic(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 11)
            {
                Console.WriteLine("Error: RandomizeMagic() -> settings doesn't have 11 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Magic...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_magoff = new("(?s)(\\x70\\x00{3})([\\x01-\\x17])(\\x00)([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)\\x00(\\x00{0,3})(\\x00[\\s\\S]{2}\\x00|[\\x00-\\xff]{4})([\\s\\S][\\x00\\x01])([\\s\\S]{4})[\\s\\S]{2}");
            Regex rgx_magdef = new("(?s)(\\x72\\x00{3})([\\x01-\\x13])(\\x00)([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)\\x00(\\x00{0,3})(\\x00[\\s\\S]{2}\\x00|[\\x00-\\xff]{4})([\\s\\S][\\x00\\x01])([\\s\\S]{4})[\\s\\S]{2}");
            Regex rgx_magfield = new("(?s)(\\x74\\x00{3})([\\x01-\\x26])(\\x00)([\\s\\S]{2})([0-9A-Za-z\\+\\'\\x20\\-]+)\\x00(\\x00{0,3})(\\x00[\\s\\S]{2}\\x00|[\\x00-\\xff]{4})([\\s\\S][\\x00\\x01])([\\s\\S]{4})[\\s\\S]{2}");

            Random RNG = new((int)settings[0]);


            // Tell the user it's done randomizing equipment.
            Console.WriteLine("Done.");

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[10]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == OFFENSE MAGIC TABLE == "); outputLog.Close(); } }

            // Offense Magic Regex Search
            MatchCollection offensive = rgx_magoff.Matches(fileString, LocStatsMagicOffense[version]);
            foreach (Match o in offensive)
            {
                // Split the groups found using Regex
                GroupCollection g = o.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsMagicOffense[version] + 0x2A4) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[5].Value;
                int[] price = new int[2] { fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8) + (fileData[g[7].Index + 2] << 16) + (fileData[g[7].Index + 3] << 24), 0 };
                short[] potency = new short[2] { (short)(fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                potency[1] = potency[0];
                // Is Magic potency seriously randomized?
                if ((bool)settings[5]) potency[1] = (short)RNG.Next(10, 300);

                // Multiply and Clamp the Potency
                potency[1] = (short)Math.Clamp((int)((float)potency[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[7]) * (float)settings[6]), 10, 900);

                // Write data to file

                // Price
                fileData[g[7].Index] = (byte)((price[1]) % 0x100);
                fileData[g[7].Index + 1] = (byte)((price[1] >> 8) % 0x100);
                fileData[g[7].Index + 2] = (byte)((price[1] >> 16) % 0x100);
                fileData[g[7].Index + 3] = (byte)((price[1] >> 24) % 0x100);

                // Potency
                fileData[g[8].Index] = (byte)((potency[1]) % 0x100);
                fileData[g[8].Index + 1] = (byte)((potency[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Off.Magic ID #: " + item_id);
                        outputLog.WriteLine("Off.Magic Name: " + name);
                        outputLog.WriteLine("Off.Magic Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Off.Magic Potency: " + (float)potency[0]/100.0f + " -> " + (float)potency[1]/100.0f);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            if ((bool)settings[10]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == DEFENSE MAGIC TABLE == "); outputLog.Close();} }

            // Defense Magic Regex Search
            MatchCollection defensive = rgx_magdef.Matches(fileString, LocStatsMagicDefense[version]);
            foreach (Match d in defensive)
            {
                // Split the groups found using Regex
                GroupCollection g = d.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsMagicDefense[version] + 0x250) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[5].Value;
                int[] price = new int[2] { fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8) + (fileData[g[7].Index + 2] << 16) + (fileData[g[7].Index + 3] << 24), 0 };
                short[] potency = new short[2] { (short)(fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                potency[1] = potency[0];
                // Is Magic potency seriously randomized?
                if ((bool)settings[5]) potency[1] = (short)RNG.Next(0, 50);

                // Multiply and Clamp the Potency
                potency[1] = (short)Math.Clamp((int)((float)potency[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[8]) * (float)settings[6]), 0, 100);

                // Write data to file

                // Price
                fileData[g[7].Index] = (byte)((price[1]) % 0x100);
                fileData[g[7].Index + 1] = (byte)((price[1] >> 8) % 0x100);
                fileData[g[7].Index + 2] = (byte)((price[1] >> 16) % 0x100);
                fileData[g[7].Index + 3] = (byte)((price[1] >> 24) % 0x100);

                // Potency
                fileData[g[8].Index] = (byte)((potency[1]) % 0x100);
                fileData[g[8].Index + 1] = (byte)((potency[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Def.Magic ID #: " + item_id);
                        outputLog.WriteLine("Def.Magic Name: " + name);
                        outputLog.WriteLine("Def.Magic Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Def.Magic Potency: " + (float)potency[0] / 100.0f + " -> " + (float)potency[1] / 100.0f);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Field Magic Regex Search
            MatchCollection field = rgx_magfield.Matches(fileString, LocStatsMagicField[version]);
            foreach (Match f in field)
            {
                // Split the groups found using Regex
                GroupCollection g = f.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsMagicField[version] + 0x480) { break; }

                // Pull out the values from each relevant group
                byte item_id = fileData[g[2].Index];
                string name = g[5].Value;
                int[] price = new int[2] { fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8) + (fileData[g[7].Index + 2] << 16) + (fileData[g[7].Index + 3] << 24), 0 };
                short[] potency = new short[2] { (short)(fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8)), 0 };

                // Make sure the default price is set
                price[1] = price[0];
                // Are the prices randomized?
                if ((bool)settings[1])
                {
                    // Are the prices seriously randomized?
                    if ((bool)settings[2])
                    {
                        price[1] = RNG.Next((int)settings[4], 99999999);
                    }

                    // Multiply and Clamp the price
                    price[1] = Math.Clamp((int)((float)price[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3])), (int)settings[4], 99999999);
                }

                // Make sure the default stats are set
                potency[1] = potency[0];
                // Is Magic potency seriously randomized?
                if ((bool)settings[5]) potency[1] = (short)RNG.Next(10, 300);

                // Multiply and Clamp the Potency
                potency[1] = (short)Math.Clamp((int)((float)potency[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[9]) * (float)settings[6]), 10, 900);

                // Write data to file

                // Price
                fileData[g[7].Index] = (byte)((price[1]) % 0x100);
                fileData[g[7].Index + 1] = (byte)((price[1] >> 8) % 0x100);
                fileData[g[7].Index + 2] = (byte)((price[1] >> 16) % 0x100);
                fileData[g[7].Index + 3] = (byte)((price[1] >> 24) % 0x100);

                // Potency
                fileData[g[8].Index] = (byte)((potency[1]) % 0x100);
                fileData[g[8].Index + 1] = (byte)((potency[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[10])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Fld.Magic ID #: " + item_id);
                        outputLog.WriteLine("Fld.Magic Name: " + name);
                        outputLog.WriteLine("Fld.Magic Price: " + price[0] + "G -> " + price[1] + "G");
                        outputLog.WriteLine("Fld.Magic Potency: " + (float)potency[0] / 100.0f + " -> " + (float)potency[1] / 100.0f);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Tell the user it's done randomizing magic.
            Console.WriteLine("Done.");

            fileString = "";
            return fileData;
        }

        // Player Class Randomizer function
        public static byte[] RandomizeClasses(int version, string filePath, byte[] fileData, List<object> settings)
        {
            // If you don't supply the right settings, just fallback to original data.
            if (settings.Count() != 8)
            {
                Console.WriteLine("Error: RandomizeClasses() -> settings doesn't have 8 values.");
                return fileData;
            }

            Console.WriteLine("Randomizing Player Classes...");
            // I'm not going to explain the Regex here, it's complicated.
            Regex rgx_base = new("(?s)(\\x40\\x00{3})([\\x00-\\x0A])([\\x00\\x01])([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})");
            Regex rgx_levelup = new("(?s)(\\x3B\\x00{3})([\\x00-\\x0A])([\\x00\\x01])([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{2})([\\s\\S]{12})");
            Regex rgx_salary = new("(?s)(\\x2E\\x00{3})([\\x00-\\x0A])([\\x00\\x01])([\\s\\S]{2})([\\s\\S]{2})\\x00\\x00([\\s\\S]{2})([\\s\\S]{2})");
            Regex rgx_capacity = new("(?s)(\x44\x00{3})([\x00-\x0A])([\x00\x01])([\x04-\x0c])([\x04-\x0c])");

            Random RNG = new((int)settings[0]);

            // Create File String
            string fileString = Convert(fileData);

            // Write to output log, if it exists
            StreamWriter outputLog;
            if ((bool)settings[7]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == CLASS BASE STATS TABLE == "); outputLog.Close(); } }

            // Player Class Base Stats Regex Search
            MatchCollection classbase = rgx_base.Matches(fileString, LocStatsClassesBase[version]);
            foreach (Match b in classbase)
            {
                // Split the groups found using Regex
                GroupCollection g = b.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsClassesBase[version] + 0x160) { break; }

                // Pull out the values from each relevant group
                byte type = fileData[g[2].Index];
                byte gender = fileData[g[3].Index];
                short[] atk = new short[2] { (short)(fileData[g[4].Index] + (fileData[g[4].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[5].Index] + (fileData[g[5].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[6].Index] + (fileData[g[6].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8)), 0 };

                // Make sure the default stats are set
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];

                // Are Player Class stats seriously randomized?
                if ((bool)settings[1])
                {
                    atk[1] = (short)RNG.Next(1, 10);
                    def[1] = (short)RNG.Next(1, 10);
                    mag[1] = (short)RNG.Next(1, 10);
                    spd[1] = (short)RNG.Next(1, 10);
                }

                // Multiply and Clamp each stat
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 30);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 30);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 30);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[3]) * (float)settings[2]), 1, 30);

                // Write data to file

                // Attack
                fileData[g[4].Index] = (byte)(atk[1] % 0x100);
                fileData[g[4].Index + 1] = (byte)((atk[1] >> 8) % 0x100);

                // Defense
                fileData[g[5].Index] = (byte)(def[1] % 0x100);
                fileData[g[5].Index + 1] = (byte)((def[1] >> 8) % 0x100);

                // Magic
                fileData[g[6].Index] = (byte)(mag[1] % 0x100);
                fileData[g[6].Index + 1] = (byte)((mag[1] >> 8) % 0x100);

                // Speed
                fileData[g[7].Index] = (byte)(spd[1] % 0x100);
                fileData[g[7].Index + 1] = (byte)((spd[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[7])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Class Type ID #: " + type);
                        outputLog.WriteLine("Class Gender ID #: " + gender);
                        outputLog.WriteLine("Base Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Base Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Base Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Base Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[7]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == CLASS LEVELUP STATS TABLE == "); outputLog.Close(); } }

            // Player Class Levelup Stats Regex Search
            MatchCollection classlevelup = rgx_levelup.Matches(fileString, LocStatsClassesLevelups[version]);
            foreach (Match l in classlevelup)
            {
                // Split the groups found using Regex
                GroupCollection g = l.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsClassesLevelups[version] + 0x2A0) { break; }

                // Pull out the values from each relevant group
                byte type = fileData[g[2].Index];
                byte gender = fileData[g[3].Index];
                short[] atk = new short[2] { (short)(fileData[g[4].Index] + (fileData[g[4].Index + 1] << 8)), 0 };
                short[] def = new short[2] { (short)(fileData[g[5].Index] + (fileData[g[5].Index + 1] << 8)), 0 };
                short[] mag = new short[2] { (short)(fileData[g[6].Index] + (fileData[g[6].Index + 1] << 8)), 0 };
                short[] spd = new short[2] { (short)(fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8)), 0 };
                short[] hp = new short[2] { (short)(fileData[g[8].Index] + (fileData[g[8].Index + 1] << 8)), 0 };

                // Make sure the default levelup stats are set
                atk[1] = atk[0];
                def[1] = def[0];
                mag[1] = mag[0];
                spd[1] = spd[0];
                hp[1] = hp[0];

                // Are Player Class Levelup stats seriously randomized?
                if ((bool)settings[1])
                {
                    atk[1] = (short)RNG.Next(0, 5);
                    def[1] = (short)RNG.Next(0, 5);
                    mag[1] = (short)RNG.Next(0, 5);
                    spd[1] = (short)RNG.Next(0, 5);
                    hp[1] = (short)RNG.Next(0, 5);
                }

                // Multiply and Clamp each levelup stat
                atk[1] = (short)Math.Clamp((int)((float)atk[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[4]) * (float)settings[2]), 0, 10);
                def[1] = (short)Math.Clamp((int)((float)def[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[4]) * (float)settings[2]), 0, 10);
                mag[1] = (short)Math.Clamp((int)((float)mag[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[4]) * (float)settings[2]), 0, 10);
                spd[1] = (short)Math.Clamp((int)((float)spd[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[4]) * (float)settings[2]), 0, 10);
                hp[1] = (short)Math.Clamp((int)((float)hp[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[4]) * (float)settings[2]), 0, 10);

                // Write data to file

                // Attack
                fileData[g[4].Index] = (byte)(atk[1] % 0x100);
                fileData[g[4].Index + 1] = (byte)((atk[1] >> 8) % 0x100);

                // Defense
                fileData[g[5].Index] = (byte)(def[1] % 0x100);
                fileData[g[5].Index + 1] = (byte)((def[1] >> 8) % 0x100);

                // Magic
                fileData[g[6].Index] = (byte)(mag[1] % 0x100);
                fileData[g[6].Index + 1] = (byte)((mag[1] >> 8) % 0x100);

                // Speed
                fileData[g[7].Index] = (byte)(spd[1] % 0x100);
                fileData[g[7].Index + 1] = (byte)((spd[1] >> 8) % 0x100);

                // Health
                fileData[g[8].Index] = (byte)(hp[1] % 0x100);
                fileData[g[8].Index + 1] = (byte)((hp[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[7])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Class Type ID #: " + type);
                        outputLog.WriteLine("Class Gender ID #: " + gender);
                        outputLog.WriteLine("Level Up Attack: " + atk[0] + " -> " + atk[1]);
                        outputLog.WriteLine("Level Up Defense: " + def[0] + " -> " + def[1]);
                        outputLog.WriteLine("Level Up Magic: " + mag[0] + " -> " + mag[1]);
                        outputLog.WriteLine("Level Up Speed: " + spd[0] + " -> " + spd[1]);
                        outputLog.WriteLine("Level Up Health: " + hp[0] + " -> " + hp[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[7]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == CLASS SALARY TABLE == "); outputLog.Close(); } }

            // Player Class Salary Regex Search
            MatchCollection classsalary = rgx_salary.Matches(fileString, LocStatsClassesSalary[version]);
            foreach (Match s in classsalary)
            {
                // Split the groups found using Regex
                GroupCollection g = s.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsClassesSalary[version] + 0x160) { break; }

                // Pull out the values from each relevant group
                byte type = fileData[g[2].Index];
                byte gender = fileData[g[3].Index];
                short[] salary = new short[2] { (short)(fileData[g[5].Index] + (fileData[g[5].Index + 1] << 8)), 0 };
                short[] smallbonus = new short[2] { (short)(fileData[g[6].Index] + (fileData[g[6].Index + 1] << 8)), 0 };
                short[] bigbonus = new short[2] { (short)(fileData[g[7].Index] + (fileData[g[7].Index + 1] << 8)), 0 };

                // Make sure the default salary data is set
                salary[1] = salary[0];
                smallbonus[1] = smallbonus[0];
                bigbonus[1] = bigbonus[0];

                // Are Player Class Salaries seriously randomized?
                if ((bool)settings[1])
                {
                    salary[1] = (short)(RNG.Next(1, 50) * 10);
                    smallbonus[1] = (short)(RNG.Next(5, 250) * 10);
                    bigbonus[1] = (short)(RNG.Next(10, 500) * 10);
                }

                // Multiply and Clamp salary data
                salary[1] = (short)Math.Clamp((int)((float)salary[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[5]) * (float)settings[2]), 10, 1500);
                smallbonus[1] = (short)Math.Clamp((int)((float)smallbonus[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[5]) * (float)settings[2]), 50, 7500);
                bigbonus[1] = (short)Math.Clamp((int)((float)bigbonus[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[5]) * (float)settings[2]), 100, 15000);

                // Make sure the Big Bonus is at least than double the Small Bonus
                if( bigbonus[1] <= smallbonus[1] * 2 ) { bigbonus[1] = (short)(smallbonus[1] * 2); }

                // Write data to file

                // Salary
                fileData[g[5].Index] = (byte)(salary[1] % 0x100);
                fileData[g[5].Index + 1] = (byte)((salary[1] >> 8) % 0x100);

                // Small Bonus
                fileData[g[6].Index] = (byte)(smallbonus[1] % 0x100);
                fileData[g[6].Index + 1] = (byte)((smallbonus[1] >> 8) % 0x100);

                // Big Bonus
                fileData[g[7].Index] = (byte)(bigbonus[1] % 0x100);
                fileData[g[7].Index + 1] = (byte)((bigbonus[1] >> 8) % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[7])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Class Type ID #: " + type);
                        outputLog.WriteLine("Class Gender ID #: " + gender);
                        outputLog.WriteLine("Salary Base: " + salary[0] + "G -> " + salary[1] + "G");
                        outputLog.WriteLine("Salary Sm.Bonus: " + smallbonus[0] + "G -> " + smallbonus[1] + "G");
                        outputLog.WriteLine("Salary Lg.Bonus: " + bigbonus[0] + "G -> " + bigbonus[1] + "G");
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Write to output log, if it exists
            if ((bool)settings[7]) { using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt")) { outputLog.WriteLine("\n\n == CLASS CAPACITY TABLE == "); outputLog.Close(); } }

            // Player Class Inventory Regex Search
            MatchCollection classinventory = rgx_capacity.Matches(fileString, LocStatsClassesCapacity[version]);
            foreach (Match i in classinventory)
            {
                // Split the groups found using Regex
                GroupCollection g = i.Groups;

                // Check if over a specific distance in the file, then break if it is.
                if (g[0].Index >= LocStatsClassesCapacity[version] + 0xB0) { break; }

                // Pull out the values from each relevant group
                byte type = fileData[g[2].Index];
                byte gender = fileData[g[3].Index];
                short[] itemcap = new short[2] { (short)fileData[g[4].Index], 0 };
                short[] magiccap = new short[2] { (short)fileData[g[5].Index], 0 };

                // Make sure the default capacities are set
                itemcap[1] = itemcap[0];
                magiccap[1] = magiccap[0];

                // Are Player Class Inventory Capacities seriously randomized?
                if ((bool)settings[1])
                {
                    itemcap[1] = (short)(RNG.Next(3, 6) * 2);
                    magiccap[1] = (short)(RNG.Next(2, 6) * 2);
                }

                // Multiply and Clamp capacities
                itemcap[1] = (short)Math.Clamp((int)((float)itemcap[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[6]) * (float)settings[2]), 6, 12);
                magiccap[1] = (short)Math.Clamp((int)((float)magiccap[1] * (1.0f + (float)RNG.Next(-100, 100) / 100.0f * (float)settings[6]) * (float)settings[2]), 4, 12);

                // Write data to file

                // Item Capacity
                fileData[g[4].Index] = (byte)(itemcap[1] % 0x100);

                // Field Magic Capacity
                fileData[g[5].Index] = (byte)(magiccap[1] % 0x100);

                // Write to Output Log in Detail, if enabled
                if ((bool)settings[7])
                {
                    using (outputLog = File.AppendText(filePath + "_" + (int)settings[0] + ".txt"))
                    {
                        outputLog.WriteLine("Class Type ID #: " + type);
                        outputLog.WriteLine("Class Gender ID #: " + gender);
                        outputLog.WriteLine("Item Capacity: " + itemcap[0] + " -> " + itemcap[1]);
                        outputLog.WriteLine("Magic Capacity: " + magiccap[0] + " -> " + magiccap[1]);
                        outputLog.WriteLine("");
                        outputLog.Close();
                    }
                }
            }

            // Tell the user it's done randomizing player classes.
            Console.WriteLine("Done.");

            fileString = "";
            return fileData;
        }

        // Converts ByteArrays directly to Strings, instead of encoding them. Required, since encoding them reformats the text output.
        static string Convert(byte[] data)
        {
            char[] chars = data.Select(c => (char)c).ToArray();
            return new string(chars);
        }
    }
}