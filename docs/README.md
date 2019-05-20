# Links

> invite

# Configuration

#### Member join and leave messages

Set the channel where join and leave messages are sent in.

> \>welcomeconfig channel <textchannel\>

Set a custom welcome message.   
Use `{user}` or `{mention}` as placeholders to be filled with the user who joined.

> \>welcomeconfig message <text...>

Enables or disables the welcome messages.

> \>welcomeconfig [ enable | disable ]

#### Starboard

React to a message with a star.    
Once it reaches certain amount of stars (default 3), it will be posted on the starboard!

Set the starboard channel.

> \>starboard channel <textchannel\>

Change the amount of required reactions.

> \>starbard amount <number\>

Enable or disable the starboard functionality

> \>starboard [ enable | disable ]

#### Votechannels

Messages posted on votechannels will automatically get upvote and downvote reactions.    
Useful in suggestion channels and such.

> \>votechannel [ add | remove ] <textchannel\>    

#### Roles

Set the role added when muting someone.    
For proper muterole configuration you must disable `send messages` for the role in every channel.

> \>muterole <role\>

Set the role applied automatically for new members who join the server.

> \>autorole <role\>

#### Other

Disable or enable levelup messages.    
Your levels will still be calculated in the background.

> \>levelupmessages [ enable | disable ]

---

# Rolepicker

Designate a channel for picking roles and assign them to keywords.  
Once set up, using `+keyword` or `-keyword` in the channel will change your roles accordingly.

> \>rolepicker channel <textchannel\>

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

> \>fishy <member\>

See the fishy leaderboard.

> \>leaderboard    
> \>leaderboard global

See statistics about your or other user's fishing.

> \>fishystats    
> \>fishystats <member\>
> \>fishystats global

---

# Info

Get basic information about the bot.

> \>info

Patreon link and the list of supporters.

> \>patreon  
> \>patrons

Get the bot's ping.

> \>ping

See statistics of the bot like uptime and memory usage.

> \>status

Github commit history.

> \>changelog

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

---

# Notifications

Set specific keywords as notifications, so you will get notified when someone mentions them in the server.  
All information will be delivered to you in private messages so others wont know your keywords.

> \>notification add <keyword>  
> \>notification remove <keyword>

Lists all your notification keywords.

> \>noification list

---

# Media

Analyze a spotify playlist from the URI or url.

> \>spotify <URI\> [amount]

Get realtime / daily / monthly chart from Melon.

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

Embeds the given post in discord so you can easily save all the images in high resolution, or just show them. You can use full url, or just the post id.

> \>ig <url\>  
> \>ig <id\>

> \>twitter <url\>  
> \>twitter <id\>

#### Web search

Search various places on the web like gfycat and youtube.

> \>gif <search...\>

> \>youtube <search...\>

> \>wikipedia <search...\>

> \>google <search...\>

---

# Users and levels

#### About XP

Every message you send will net you a certain amount of experience, based on the word count of your message. Posting images will also get you xp.  
Once you gain enough experience, you will level up. The amount of experience required for leveling up will increase every time.  
The bot will start counting xp from the moment it's invited, so past messages wont matter. In case you want past messages to be counted, just ask and I will index your server. (< 100 000 messages)

---
Shows your server activity graph per hour, along with your xp and level information.

> \>activity

Get the activity leaderboard. Shows the users with most xp on this server (or globally).

> \>toplevels  
> \>toplevels global

Get user's profile picture.

> \>avatar <user\>

User information.

> \>userinfo <user>

---

# Server

Show the newest members of the server.

> \>members

Get information about the server.

> \>serverinfo

---

# Images

Input text into various meme images. (currently just one).

> \>olivia <text...>

---

# Miscellaneous Commands

Gets random number between 0 and the max value.  
When used without max value, will return either 0 or 1.

> \>rng  
> \>rng <max\>

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

Pewdiepie VS T-series current subscribers.

> \>pewdiepie

Get the current status of any minecraft server.  
You can usually not specify any port and it will work with the default.

> \>minecraft <address\> <port\>

#### Horoscope

Get your daily horoscope. Save your sunsign by using `set`.  
List all sunsigns and their ranges by using `list`.

> \>horoscope  
> \>horoscope set  
> \>horoscope list
