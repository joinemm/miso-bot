###### Documentation updated 01/09/2020

# Syntax

This page will list most of the commands this bot has to offer.   
Argument syntax is as follows:   

`<required>`    
`[optional]`

Do not include the brackes in the command.   

Aguments are split on whitespace, unless surrounded by quotes `"like this"`.    
Arguments affixed with `...` on this page do not need quotes but are instead parsed till the end of line.

# Info

Get basic information about the bot.

> \>info

Patreon link and the list of supporters.

> \>patreon  
> \>patrons

Get the bot's ping.

> \>ping

See statistics of the bot.

> \>system    
> \>stats

Github commit history.

> \>changelog

Statistics about command usage.

> \>commandstats server [user]    
> \>commandstats global [user]    
> \>commandstats <command\>

Statistics about emoji usage.

> \>emojistats [user]    
> \>emojistats global [user]

Get MONDAY invite link.

> \>invite

---

# Rolepicker

Designate a channel for picking roles and assign them to keywords.  
Once set up, using `+keyword` or `-keyword` in the channel will change your roles accordingly.

> \>rolepicker channel <textchannel\>

Enable and disable the rolepicker

> \>rolepicker [ enable | disable ]

Add and remove assignable roles.

> \>rolepicker add <role\> <keyword\>    
> \>rolepicker remove <keyword\>

List all the roles currently available in the rolepicker.

> \>rolepicker list

---

# Fishy

Go fishing and receive random fish.

> \>fishy

You can also gift fishy to other members:

> \>fishy [member]

Check your fishy timer without actually fishing.

> \>fishytimer

See statistics about your or other user's fishing.

> \>fishystats [member]    
> \>fishystats global

---

# Custom Commands

Custom commands specific to a server.    
Give a command name and the response message.

> \>command add <name\> <response...\>    
> \>command remove <name\>

Get list of custom commands added on this server.

> \>command list

Search for a command by keyword. Will also find built-in commands.

> \>command search <keyword...\>

---

# Moderation

Mute member. Adds the muterole you have set for the given user.  
Optionally specify a time for long to mute.

> \>mute <member\> [duration...]  
> \>unmute <member\>

Permanently ban a user. Doesn't have to be a member of the server.

> \>ban <user\>

Bulk delete messages. Mention users at the end to only delete messages by them. Amount determines how many messages up to scan.

> \>purge <amount\> [mentions...]

Blacklist users, commands and channels.

> \>blacklist user <member...\>    
> \>blacklist channel <textchannel...\>    
> \>blacklist command <command...\>    
> \>blacklist show    

Toggle whether command usage that triggers a blacklist will be automatically deleted.

> \>blacklist delete <boolean\>    

Reverse any blacklisting you might have done

> \>whitelist user <member...\>    
> \>whitelist channel <textchannel...\>    
> \>whitelist command <command...\>    

---

# Notifications

Set specific keywords as notifications, so you will get notified when someone mentions them in the server.  
All information will be delivered to you in private messages so others wont know your keywords.

> \>notification add <keyword>    
> \>notification remove <keyword>

Lists all your notification keywords.

> \>notification list

---

# Media

Melon music charts.

> \>melon <timeframe\>

Get a random or specific xkcd comic.

> \>xkcd    
> \>xkcd <id\>

#### Colors

Get a hex color, the color of a member or role, color from image, or a random color.  
You can chain any of these sources together to form a palette.

> \>color <#hex>    
> \>color <member\>    
> \>color <role\>    
> \>color <image_url\>    
> \>color random [amount]

#### Social media

Embeds the given post in discord so you can easily save all the images in high resolution, or just show them.    
You can use full url, or just the post id. (eg. `1156225603470688261` for twitter or `B0u02QonS3z` for instagram)

> \>instagram <url | id\>  

> \>twitter <url | id\>  

You can use `-d` or `--download` flag with twitter and instagram to download and reupload the images.    
These images are named for easy downloading and will not stop working in case the original tweet is deleted.

> \>instagram <url | id\> --download    
> \>twitter <url | id\> --download

#### Web search

Search various places on the web like gfycat and youtube.

> \>gif <search...\>

> \>youtube <search...\>

> \>wikipedia <search...\>

> \>google <search...\>

#### DuckDuckGo

Use any DuckDuckGo [bangs](https://duckduckgo.com/bang) to quickly search the internet!

> \>!<bang\> <search...\>

---

# LastFM

Integration with the music tracking service Last.fm. For anything requiring artist name, the name must be formatted **exactly** as is shows up in the lastfm website. For most commands, artist or song names can be replaced with `np` and it will automatically use your currently playing song.

You can mention anyone at the end of an command, making sure it doesn't conflict with other arguments, and you will see the mentioned user's stats instead, as long as they have connected their last.fm username.

First connect your lastfm account by using

> \>fm set <username\>

Check your profile with 

> \>fm profile

Then you can check various top lists.

> \>fm toptracks [timeframe]    
> \>fm topartists [timeframe]    
> \>fm topalbums [timeframe]    

Valid timeframes are `[day | week | month | 3month | 6month | year | alltime]` (defaults to alltime)

Show your most recently listened to tracks, or the one currently playing in embed or youtube link form.

> \>fm recent    
> \>fm nowplaying    
> \>fm youtube

Generate a visual collage of your data.    
You can optionally specify datatype `[ artist | album | recent ]`, timeframe or size of the chart.    
Defaults to albums week 3x3.

> \>fm chart [datatype] [timeframe] [size] [notitle]

Chart that is based on a hex color instead of amount of plays.

> \>fm colorchart <color\> [size]    
> \>fm colorchart [ rainbow | rainbowdiagonal ]

Check who has listened to given artist most on this server. Top listener gains a crown.

> \>whoknows <artist\>

You can also check individual songs or albums, but those will not award any crowns.

> \>whoknowstrack <track\> | <artist\>    
> \>whoknowsalbum <album\> | <artist\>

Show artist specific data from your listens.

> \>fm artist [timeframe] toptracks <artist\>    
> \>fm artist [timeframe] topalbums <artist\>

Show overview of your top tracks and albums for artist.

> \>fm artist [timeframe] overview <artist\>

Show overview of given album's tracks.

> \>fm album <album\> | <artist\>

See combined server stats.

> \>fm server nowplaying    
> \>fm server recent    
> \>fm server toptracks    
> \>fm server topartists    
> \>fm server topalbums

See your artist crowns on this server.

> \>crowns

Report someone who is botting plays for crowns. (don't abuse)

> \>report <lastfm_username\> <reason... \>

Search for song lyrics.

> \>lyrics <query\>    

Unlink you last.fm account.

> \>fm unset

---

# Users and levels

#### About XP

Every message you send will net you a certain amount of experience, based on the word count of your message. Posting images will also get you xp.  
Once you gain enough experience, you will level up. The amount of experience required for leveling up will increase every time.  
The bot will start counting xp from the moment it's invited, so past messages wont matter.

---
Shows your server activity graph per hour, along with your xp and level information.

> \>activity [user]

Shows your top servers with MONDAY bot.

> \>topservers

Show your daily/weekly/monthly/overall xp ranking

> \>rank [user]

Get user's profile picture.

> \>avatar [user] 

User information.

> \>userinfo [user]

Show various leaderboards

> \>leaderboard levels [global] <timeframe\>    
> \>leaderboard fishy [global]    
> \>leaderboard crowns    
> \>leaderboard wpm [global]

Your personal profile.

> \>profile [user]

Edit your profile.

> \>editprofile description <text...\>    
> \>editprofile background <image url\>
---

# Server

Show the newest members of the server.

> \>members

Get information about the server.

> \>serverinfo

Get list of all roles on the server, and information about them.

> \>roleslist

Get server's icon.

> \>servericon

---

# Images

Input text into various meme images.

> \>meme <variant\> <text...\>

---

# Utility Commands

#### Host services

Create a gfycat gif from a video url / twitter link / instagram link.

> \>creategif <video\>

Create streamable link from a video url / twitter link / instagram link.

> \>streamable <video\>

#### Definitions

Get a definition for a word from the Oxford Dictionary.

> \>define <word\>

Get synonyms for a word.

> \>thesaurus <word\>

Get a definition for a word from the Urban Dictionary.

> \>urban <word\>

#### Translator

Translate any text between any two languages.   
Uses Papago translator for all supported languages (most asian languages), and Google translate for anything not supported by Papago.

You can optionally specify the two languages in the start using the format `xx/xx` where `xx` are language codes.    
Either of them can be left blank; If the first language is left blank, the source language will be automatically detected from the given text.    
If the target language is left blank, it will default to english.

> \>translate xx/xx <text...\>    
> \>translate /xx <text...\>    
> \>translate <text...\>    

#### Misc 

Get current weather, and brief forecast for any location.    
You can also save your location so you dont have to specify it every time.

> \>weather <location\>    
> \>weather save <location\>

Ask something from wolfram alpha.    

> \>wolfram <query...>

Set a reminder, and MONDAY will remind you!

> \>remindme in <some time\> to <something\>    
> \>remindme on <YYYY/MM/DD\> [HH:mm:ss] to <something\>

US stock market data.

> \>stock <ticker\>    
> \>stock <company\>

---

# Typing tests

Take a typing test.

> \>typing test [language] [wordcount]

Race against other people.

> \>typing race [language] [wordcount]

See your stats or history.

> \>typing stats    
> \>typing history

---

# Miscellaneous Commands

Gets random number between 0 and the max value.  
When used without values, will return either 0 or 1.

> \>rng [min] [max]

Turn text into fancy ascii art.

> \>ascii <text...>

Ask a yes or no question from the 8ball.

> \>8ball <question...>

hug someone or something.

> \>hug <text...\>

Choose from given options. Give as many options as you want, separated with `or`.

> \>choose <option_1\> or <option_2\> or ... <option_n\>

Get a random kpop artist that you should totally stan.

> \>stan

Ship two people and get their love% from 0% to 100%. Separate the names with 'and'.

> \>ship <name\> and <name\>

Get the current status of any minecraft server.  
You can usually not specify any port and it will work with the default.

> \>minecraft <address\> <port\>

Add clap emojis between words.

> \>clap <message...\>

Get big image and info about some emoji.

> \>emoji <:emoji:\>

#### Horoscope

Get your daily horoscope. Save your sunsign by using `set`.  
List all sunsigns and their ranges by using `list`.

> \>horoscope
> \>horoscope [ tomorrow | yesterday ]
> \>horoscope set  
> \>horoscope list

#### OPGG

League of Legends summoner profile.

> \>opgg profile <region\> <summoner name...\>    
> \>opgg nowplaying <region\> <summoner name...\>    

---

# Configuration

#### Change prefix

Don't like `>`? Don't worry you can now change it to whatever you want.

> \>prefix <something\>

#### Automatic messages

Logger sends various automatic messages.

> \>logger

Welcome and goodbye messages.

> \>logger welcome channel <textchannel\>    
> \>logger goodbye channel <textchannel\>

> \>logger welcome message <message...\>    
> \>logger goodbye message <message...\>    

You can use these placeholders in message and they will be filled accordingly:
- `{user}` = full username with #1234 discriminator    
- `{username}` = username    
- `{mention}` = user mention    
- `{guild}` = server name    
- `{server}` = server name    
- `{guild}` = user's ID

Change whether welcome message is wrapped in an embed or not.

> \>logger welcome embed <boolean\>

Log deleted messages to a channel.

> \>logger deleted channel <textchannel\>

Ignore certain channels from deleted messages logging.

> \>logger deleted [ ignore | unignore ] <textchannel\>

Send message when user gets banned.

> \>logger bans <textchannel\>

Enable or disable levelup messages.

> \>logger levelups <boolean\>

Enable or disable automatic responses to certain messages.

> \>autoresponses <boolean\>

#### Starboard

React to a message with a star.    
Once it reaches certain amount of stars (default 3), it will be posted on the starboard!

Set the starboard channel.

> \>starboard channel <textchannel\>

Change the amount of required reactions.

> \>starboard amount <number\>

Enable or disable the starboard functionality

> \>starboard [ enable | disable ]

Change emoji used to trigger the starboard

> \>starboard emoji <:emoji:\>

#### Votechannels

Messages posted on votechannels will automatically get upvote and downvote reactions.    
Useful in suggestion channels and such.

> \>votechannel [ add | remove ] <textchannel\>    

Change the type of voting channel (up/down votes or ranking from 0 to 5)

> \>votechannel type [ vote | rate ]

#### Roles

Set the role added when muting someone.    
For proper muterole configuration you must disable `send messages` for the role in every channel.

> \>muterole <role\>   
> \>muterole none

Set the role applied automatically for new members who join the server.

> \>autorole <role\>   
> \>autorole none
