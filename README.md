# DOKAPON KINGDOM RANDOMIZER
Version 3.0

## REQUIREMENTS
.NET 7.0 Runtime: https://dotnet.microsoft.com/en-us/download/dotnet/7.0

## HOW TO USE

This randomizer works with the PC (Steam) version of Dokapon Kingdom Connect. The Wii version is no longer supported.
You'll want to have a zip archive extracter at the ready. I recommend 7zip.

### Steps:
1) Obtain a copy of Dokapon Kingdom Connect from Steam. I'm unsure of other potential storefronts that may have it.
2) Download "Connect Mod Installer" and "Yet Another CPK Tool". Both can be found on Github and through some potential google searching. Read their instructions to learn how they work.
3) Drag and drop "Data_eng.cpk" onto "Yet Another CPK Tool" to extract its data.
4) After extraction, search the newly created folders for "stageBase_EN.dat" and copy it to where your copy of the Randomizer is located.
5) Run the randomizer. When prompted, make a backup, just in case. Follow the remainder of the steps to fill out what options you want.
6) Once you're done, move the altered "stageBase_EN.dat" into an "Assets" folder inside another folder with a name of your choice, then move that folder to inside of the "Connect Mod Installer" Mods folder.
7) Run "Connect Mod Installer" and point it to your Dokapon Kingdom Connect executable.

If you turned on Weapon Special Effects, the randomizer also writes a "Hex" folder (next to your "Assets" folder, inside the mod folder) containing "weapon_effects.hex". Keep it there: Connect Mod Installer applies it to the game executable. It only fits the current Steam build of the game.

## OPTIONS
- Making a Backup (Boolean):
	This allows you to save a backup of your extracted file whereever it's located before writing to it.

- Shuffling Equipment (Boolean):
	Instead of rolling new numbers, this swaps which item sits in which slot, within each pool (Weapons with Weapons, Shields with Shields, Accessories with Accessories). Every slot keeps its ID, Price, and Stats, so the power curve of the game is unchanged, but the item's identity (name, type, and ability data) moves. The Knife's tutorial slot might hand you a Kitten Mitten with the Knife's Stats and Price.
	Can be combined with Randomizing Equipment, in which case the shuffle happens first.

- Shuffling Magic (Boolean):
	The same idea for Offensive, Defensive, and Field Magic, each in their own pool. Every slot keeps its ID, Price, Potency, and Cost, but the spell's identity (name, type, element, and animation/effect data) moves. A first-tier slot might hand you Teleport at Scorch's price and potency.
	Can be combined with Randomizing Magic, in which case the shuffle happens first.

- Shuffling Items (Boolean):
	Shuffles the names of Gifts for the King between Gift slots. Everything else about a Gift (Price, value to the King, sort data) stays with the slot.
	Can be combined with Randomizing Consumables/Prices, in which case the shuffle happens first.
	- Also Shuffle Consumables (Boolean, EXPERIMENTAL):
		Also shuffles Consumables between Consumable slots. Price and shop values stay with the slot, while name, category, and type move. Off by default, because the game may decide what a Consumable does by its ID rather than by its data. The numbered Crystals are identical apart from their names, so a "6 Crystal" could end up named something else and still move you 6 spaces. Test this in-game before trusting it.

- Weapon Special Effects (0 to 3, current Steam build only):
	In the base game only 22 weapons have a special effect (Sleep Bow, Dream Rod, Soul Eater and so on), tied to the weapon's ID inside the executable. This option patches the executable (through the Hex file above) so any weapon can carry any of those effects, and so an effect's chance is read from the weapon's own record instead of being fixed in the code.
	- 0: unchanged. 1: effects follow their weapon's name, which matters when Equipment is shuffled. 2: the existing effects are dealt out to different weapons. 3: every weapon gets a random effect.
	- Randomize the effects' proc chances (Boolean): Each effect gets a chance of 5% to 50% (effects that are always on stay on). If false, each effect keeps its base game chance.
	Weapon descriptions are rewritten to say what the weapon now does and its chance, for example "Cast Zapper" and "12% chance". Spell effects name the spell they cast, which follows Shuffling Magic. The other effects use generic text.
	A weapon that ends up with its own base game effect keeps its original description.

- Include Story and Unbuyable Items (Boolean, only asked if you shuffle something):
	Items with a base price of 2 or less (things like the Draco Blade, Demon Shield, and quest items) are normally left in their own slots. Turn this on to mix them in with everything else.

NOTE: Item descriptions and any effects the game hard-codes by item ID can't be moved by the shuffle options.

- Randomizing Equipment (Boolean):
	This allows you to randomize the statistics of Weapons, Shields, and Accessories.
	If enabled, you get the following options:
	- SERIOUSLY Randomize Equipment (Boolean):
		This disregards the normal stats of whatever is being randomized and pulls numbers from a randomly generated table instead, making each item have REALLY fluctuated stats.
	- Equipment Strength Multiplier (Float):
		This multiplies the end result of the stat randomization for all items by a flat value.
	- Weapon, Shield, Accessory Strength Variance (Float):
		These will either drop or increase the stats of each type of item by 0% to the specified percentile value you give it.

- Randomizing Magic (Boolean):
	This allows you to randomize the statistics of Offensive, Defensive, and Field Magic.
	If enabled, you get similar options to Equipment Randomization, but for Magic (obviously).
	- SERIOUSLY Randomize Magic (Boolean):
		This disregards the normal stats of whatever is being randomized and pulls numbers from a randomly generated table instead, making each item have REALLY fluctuated stats.
	- Magic Strength Multiplier (Float):
		This multiplies the end result of the stat randomization for all items by a flat value.
	- Offensive, Defensive, and Field Magic Strength Variance (Float):
		These will either drop or increase the stats of each type of item by 0% to the specified percentile value you give it.

- Randomizing Player Classes (Boolean):
	This allows you to randomize the statistics of Player Classes. (NOTE: Both genders count as different sets of classes! Stats are not distributed equally to both genders!)
	If enabled, you get the following options:
	- SERIOUSLY Randomize Player Classes (Boolean):
		Again, disregards the original values and replaces them with randomly generated ones.
	- Class Stats Strength Multiplier (Float):
		Multiplies the base stats of the player by a flat value. This does not affect your class' carrying capacities or base HP.
	- Class Base Stats, Level-Up Bonuses, Salary, Inventory Capacity Variance (Float):
		These work like the other variance values. I recommend setting these above zero except for the Inventory Capacity Variance since the changes are usually too small to notice. You do you though.

- Randomizing Monsters (Boolean):
	This allows you to randomize Monster statistics.
	If enabled, you get the following options:
	- SERIOUSLY Randomize Monsters (Boolean):
		Disregards the original values and replaces them with randomly generated ones.
	- Base Stats Strength Multiplier (Float):
		Multiplies the base stats of the player by a flat value. Unlike the Player Classes, this DOES affect HP.
	- Base Stats Variance (Float):
		Works like all the other variance values, increasing or decreasing stats up to the listed percentile value.

- Randomize Consumables (Boolean):
	This option allows Consumable Items' prices to be randomized.

- Randomize Shops and Drops (Boolean):
	These randomize the contents of Shops and Loot Spaces/Monster Drop Tables respectively.
	
- Randomize Prices (Boolean):
	This randomizes the price value of all items in the game.
	If enabled, you get the following options:
	- Minimum Price Value (Integer):
		The lowest value an item can cost for purchase.
	- Price Strength Variance (Float):
		Like all other variance values.
	- SERIOUSLY RANDOMIZE Consumable Item Prices (Boolean):
		Only shows up if Consumables are allowed to be randomized.
		This only affects anything you'd obtain that counts as either a Consumable (crystals, spinners, etc) or as a Gift for the King (gemstones, food, etc). It can make things insanely expensive.
	NOTE: Seriously randomizing anything with Random Prices enabled will randomize their prices dramatically.
	
- Allow Exploits (Boolean):
	This allows some exploitable Items to be put into Shops and ignores Loot Space Types in regards to Loot Space Drop Table Randomization.
	- NOT RECOMMENDED for seriously play. If you're playing casually, feel free to abuse it.

- Randomize Prank Names (Boolean, PC Only):
	This allows you to replace the Prank Names selected when pranking after PvP fights. They're chosen at-random from a list of names.
	NOTE: Please do not distribute Prank Name files with derogatory or inappropriate names. Additionally, please use Steam Remote Play or Parsec, as I have no idea how this works with Online saves.
	- The "pranknames.txt" file must remain where it is. Feel free to edit it with names. Each Prank Name can be as long as 15 characters. Anything longer will be skipped.
	
- Randomized Run Seed (String):
	The seed for the run. Optional. Will generate based on time if you don't supply one.
	
- Save Output Log (Boolean):
	This will output everything that was randomized to an output log. The file will end up varying in size depending on how much you randomize.
