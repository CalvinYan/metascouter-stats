# A proof-of-concept script that runs through a number of basic data analyses we can perform on the Metascouter API.

import requests
import numpy as np
import matplotlib.pyplot as plt
import math
import os
import seaborn as sns
import json

# We need to retrieve the API authorization via JWT token before we can do anything
pwd = os.getenv('METASCOUTER_PWD')
request = requests.post('https://api.metascouter.gg/auth/obtain-token/',
                        json={'username': 'Cyan', 'password': pwd})
if request.status_code == 200:
    token = request.json()['token']
else:
    print('ERROR RETRIEVING JWT TOKEN')
    exit()

def api_request(url):
    jwt_auth = {'Authorization': 'JWT ' + token}
    request = requests.get('https://api.metascouter.gg/ssbu/' + url, headers=jwt_auth)
    if request.status_code != 200:
        print('There was an error with the api_request.')
        print(request)
        return None
    return request.json()

def death_at_zero(match):
    for data in match['stats']['event_data']:
        for death in data['health_at_death_data']:
            if death[1] == 0:
                return True
    return False

def match_tag(match):
    return 'Match %d of set %d' % (match['index_in_set'], match['set'])

print('Welcome to the proof of concept Metascouter data analysis script!')
input('When you see the > symbol at the end of a sentence, press ENTER to advance. > ')
input('When a chart is displayed, close it to advance. > ')

print("We'll begin by pulling all set and match data from the API.")
print('Retrieving tournament data:')
tournaments = api_request('tournaments?limit=80')['results']
print('Done.')

pgru_s_a_tiers = {'Super Smash Con', 'Smash Ultimate Summit', 'The Big House', 'Genesis', 'EVO',
                  'Get On My Level', 'Evolution Japan', '2GG',
                  'Shine', 'Ultimate Summit', 'Umebura', 'Pound', "Let's Make Big Moves",
                  'Frostbite', 'Dreamhack Atlanta', 'Glitch', 'Mainstage', 'Thunder Smash'}
print('The sample size of this demo will consist of all sets from all tournaments rated A or S tier by Panda Global '
      'Rankings Ultimate that are currently in the Metascouter database. These consist of the following:')
print(pgru_s_a_tiers)
input('Press ENTER to continue. > ')
pgru_s_a_ids = {tournament['id']: tournament['name'] + ' ' + tournament['number'] for tournament in tournaments if
                tournament['name'] in pgru_s_a_tiers}

print('Retrieving set data:')
sets = []
for tid in pgru_s_a_ids.keys():
    print('Pulling all sets from', pgru_s_a_ids[tid])
    tournament = api_request('tournaments/' + str(tid))
    if tournament:
        sets.extend([t_set for t_set in tournament['sets']])
print('Done.')

input('Validating matches. Any with faulty information will be displayed below. > ')
matches = []
for t_set in sets:
    for match in t_set['matches']:
        tag = match_tag(match) + ':'

        if len(match['stats']['event_data'][0]['stock_data']) < 3 and len(
                match['stats']['event_data'][1]['stock_data']) < 3:
            print(tag, 'neither player has 3 stock events')

        elif len(match['stats']['event_data'][0]['stock_data']) > 3 or len(
                match['stats']['event_data'][1]['stock_data']) > 3:
            print(tag, 'player has more than 3 stock events')

        elif death_at_zero(match):
            print(tag, 'death at 0 percent')
        else:
            matches.append(match)

input(str(len(matches)) + ' matches successfully retrieved. > ')

print("In addition to these, we'll want to use matches in their flat form via the sets/[ID]/matches/ API enpoint.")
matches_flat = {}
for i, t_set in enumerate(sets):
    if i % 20 == 0:
        print('Retrieving set', i)
    matches_flat[t_set['id']] = []
    for match in api_request('sets/' + str(t_set['id']) + '/matches/')['results']:
        tag = match_tag(match) + ':'
        if not match['winner']:
            print(tag, 'no winner specified')
        else:
            matches_flat[t_set['id']].append(match)

print('Done.')
print("Our goal is to look for trends in the following match-specific metrics: Average death percentage, average "
      "kill percentage, stocks taken, stocks lost, total damage dealt, and total damage taken. We'll plot these over "
      "various categorical features including character, player, and player-character combination.")
input('Before we begin, note that all error bars denote a 95% confidence interval, and that data points corresponding '
      'to categorical values found in fewer than 30 matches are omitted. > ')

# The first sweep of MATCHES looks at frequencies only. How many times each player, character, and player-character
# combination shows up determines whether we can make inferences about its damage stats.
character_freq = {}
character_reps = {}
player_freq = {}
player_char_freq = {}

for match in matches:
    for player_data in match['players'].values():
        char = player_data['character']['internal_name']
        player = player_data['player_tag']
        if char not in character_freq:
            character_freq[char] = 0
            character_reps[char] = set()
        if player not in player_freq:
            player_freq[player] = 0
        if player not in player_char_freq:
            player_char_freq[player] = {}
        if char not in player_char_freq[player]:
            player_char_freq[player][char] = 0
        character_freq[char] += 1
        character_reps[char].add(player)
        player_freq[player] += 1
        player_char_freq[player][char] += 1

characters = sorted(filter(lambda key: character_freq[key] >= 30, character_freq.keys()),
                    key=lambda key: -character_freq[key])
players = sorted(filter(lambda key: player_freq[key] >= 30, player_freq.keys()), key=lambda key: -player_freq[key])
player_chars = {}

for player in players:
    player_chars[player] = sorted(
        filter(lambda key: player_char_freq[player][key] >= 30, player_char_freq[player].keys()),
        key=lambda key: -player_char_freq[player][key])

# The second sweep of MATCHES yields most of the data we want for examination. Kill percents, stocks taken/lost, and
# damage are all retrieved and categorized by win/loss, or specific players, characters, and player-character
# combinations, depending on which of these we determined to occur often enough based on the first sweep.

# This is a pretty messy way of going about things and I might clean it up with pandas DataFrames if I get around to it.

characters = sorted(characters, key=lambda x: x)
# Dictionaries/lists for storing our data
winning_damage = []
losing_damage = []
winning_death_pcts = []
losing_death_pcts = []

char_kill_pcts = {char: [] for char in characters}
char_death_pcts = {char: [] for char in characters}
player_kill_pcts = {player: [] for player in players}
player_death_pcts = {player: [] for player in players}
hybrid_kill_pcts = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}
hybrid_death_pcts = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}

char_kills = {char: [] for char in characters}
char_deaths = {char: [] for char in characters}
player_kills = {player: [] for player in players}
player_deaths = {player: [] for player in players}
hybrid_kills = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}
hybrid_deaths = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}

char_damage_dealt = {char: [] for char in characters}
char_damage_taken = {char: [] for char in characters}
player_damage_dealt = {player: [] for player in players}
player_damage_taken = {player: [] for player in players}
hybrid_damage_dealt = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}
hybrid_damage_taken = {player: {char: [] for char in player_chars[player]} for player in player_chars.keys()}

matchups = {char: {char: [] for char in characters} for char in characters}

for match in matches:

    won = [False, False]
    kill_pcts = [[], []]
    death_pcts = [[], []]
    kills = [0, 0]
    deaths = [0, 0]
    damage_dealt = [0, 0]
    damage_taken = [0, 0]
    player_arr = [None, None]
    character_arr = [None, None]

    for player_data in match['players'].values():
        if player_data['player'] == 1:
            won[0] = match['stats']['ending_player_stocks'][player_data['id']] > 0
            player_arr[0] = player_data['player_tag']
            character_arr[0] = player_data['character']['internal_name']
        else:
            won[1] = match['stats']['ending_player_stocks'][player_data['id']] > 0
            player_arr[1] = player_data['player_tag']
            character_arr[1] = player_data['character']['internal_name']

    for i in range(2):
        for stock in match['stock_stats'][str(i + 1)].values():
            damage_dealt[i] += stock['damage_dealt']
            damage_taken[1 - i] += stock['damage_dealt']

            if 'death_percent' in stock:
                death_pcts[i].append(stock['death_percent'])
                kill_pcts[1 - i].append(stock['death_percent'])
                deaths[i] += 1
                kills[1 - i] += 1

    for i in range(2):
        char = character_arr[i]
        player = player_arr[i]

        if won[i]:
            winning_damage.append(damage_dealt[i])
            winning_death_pcts.extend(death_pcts[i])
        else:
            losing_damage.append(damage_dealt[i])
            losing_death_pcts.extend(death_pcts[i])
        if char in characters:
            char_kill_pcts[char].extend(kill_pcts[i])
            char_death_pcts[char].extend(death_pcts[i])
            char_kills[char].append(kills[i])
            char_deaths[char].append(deaths[i])
            char_damage_dealt[char].append(damage_dealt[i])
            char_damage_taken[char].append(damage_taken[i])
        if player in players:
            player_kill_pcts[player].extend(kill_pcts[i])
            player_death_pcts[player].extend(death_pcts[i])
            player_kills[player].append(kills[i])
            player_deaths[player].append(deaths[i])
            player_damage_dealt[player].append(damage_dealt[i])
            player_damage_taken[player].append(damage_taken[i])
        if player in player_chars and char in player_chars[player]:
            hybrid_kill_pcts[player][char].extend(kill_pcts[i])
            hybrid_death_pcts[player][char].extend(death_pcts[i])
            hybrid_kills[player][char].append(kills[i])
            hybrid_deaths[player][char].append(deaths[i])
            hybrid_damage_dealt[player][char].append(damage_dealt[i])
            hybrid_damage_taken[player][char].append(damage_taken[i])

    char1, char2 = character_arr
    if char1 in characters and char2 in characters:
        if deaths[0] == 3:
            matchups[char1][char2].append(0)
            matchups[char2][char1].append(1)
        else:
            matchups[char2][char1].append(0)
            matchups[char1][char2].append(1)


# for match in matches:
#     for deaths in match['stock_stats'].values():
#         total_damage = sum([data['damage_dealt'] for data in deaths.values()])
#         if '1' in deaths and 'death_percent' in deaths['1']:
#             losing_damage.append(total_damage)
#             losing_deaths.extend([data['death_percent'] for data in deaths.values()])
#         else:
#             winning_damage.append(total_damage)
#             winning_deaths.extend([data['death_percent'] for data in deaths.values() if 'death_percent' in data])
# print(len(winning_damage))

fig, ax = plt.subplots()
ax.set_xlim(0, 600)
ax.set_xlabel('Damage dealt by match winner')
ax.hist(winning_damage, bins=20, color='green')
print('Mean:', np.mean(winning_damage))
print('Standard deviation:', np.std(winning_damage))
plt.show()

fig, ax = plt.subplots()
ax.set_xlim(0, 600)
ax.set_xlabel('Damage dealt by match loser')
ax.hist(losing_damage, bins=20, color='red')
ax.plot()
print('Mean:', np.mean(losing_damage))
print('Standard deviation:', np.std(losing_damage))
plt.show()

fig, ax = plt.subplots()
ax.set_xlim(0, 600)
ax.set_ylim(0, 600)

for w, l in zip(winning_damage, losing_damage):
    color = 'blue' if w >= l else 'purple'
    plt.scatter(w, l, color=color)
ax.set_xlabel('Winning damage taken')
ax.set_ylabel('Losing damage taken')
plt.show()

dmg_inversion = [w < l for w, l in zip(winning_damage, losing_damage)]
proportion = np.mean(dmg_inversion)
margin = 1.96 * math.sqrt(proportion * (1 - proportion) / len(dmg_inversion))
print('Proportion of damage inversions (winner took more damage): ', proportion, '+-', margin)
plt.show()

first_stock_wins = []
for t_set in matches_flat.values():
    for match in t_set:
        first_blood = 3 - match['stock_events_stats'][2]['player_number']
        first_stock_wins.append(match['player' + str(first_blood)]['id'] == match['winner']['id'])
proportion = np.mean(first_stock_wins)
margin = 1.96 * math.sqrt(proportion * (1 - proportion) / len(first_stock_wins))
print('Proportion of games where the taker of the first stock wins the match:', proportion, '+-', margin)
input('No associated graph for this one, just thought it was a cool tidbit. > ')

stock_diffs = [0, 0, 0, 0]
for match in matches:
    stock_diffs[sum(match['stats']['ending_player_stocks'].values())] += 1
plt.bar(['1 stock', '2 stock', '3 stock'], stock_diffs[1:])
print('Matches by stock difference:')
plt.show()

fig, ax = plt.subplots()
ax.set_xlim(0, 300)
ax.set_xlabel('Death percentage (winning player)')
ax.hist(winning_death_pcts, bins=20, color='green')
print('Mean:', np.mean(winning_death_pcts))
print('Standard deviation:', np.std(winning_death_pcts))
plt.show()

fig, ax = plt.subplots()
ax.set_xlim(0, 300)
ax.set_xlabel('Death percentage (losing player)')
ax.hist(losing_death_pcts, bins=20, color='red')
print('Mean:', np.mean(losing_death_pcts))
print('Standard deviation:', np.std(losing_death_pcts))
plt.show()

stock_diff = {'0-3': 0, '0-2': 0, '0-1': 0, '1-0': 0}

for match in matches:
    p1_stocks = match['stats']['event_data'][0]['stock_data']
    p2_stocks = match['stats']['event_data'][1]['stock_data']
    if len(p2_stocks) == 0 or len(p1_stocks) > 1 and p1_stocks[1][0] < p2_stocks[0][0]:
        stock_diff[str(3 - len(p1_stocks)) + '-' + str(3 - len(p2_stocks))] += 1
    elif len(p1_stocks) == 0 or len(p2_stocks) > 1 and p2_stocks[1][0] < p1_stocks[0][0]:
        stock_diff[str(3 - len(p2_stocks)) + '-' + str(3 - len(p1_stocks))] += 1

print('Outcome of matches with a 2-stock deficit:')
plt.bar(list(stock_diff.keys()), list(stock_diff.values()))
plt.show()
input('Proportion of 2-stock deficits that ended in a comeback: ' + str(stock_diff['1-0']/sum(stock_diff.values())) + ' > ')

outcomes = [[0, 0], [0, 0], [0, 0], [0, 0]]

for match in matches:
    for data in match['stats']['event_data']:
        num_early_deaths = sum([death[1] <= 100 for death in data['health_at_death_data']])
        #         if num_early_deaths == 3:
        #             print(match_tag(match))
        outcomes[num_early_deaths][0 if len(data['health_at_death_data']) == 3 else 1] += 1

outcomes = outcomes[:3]
print([o[0] for o in outcomes])
print([o[1] for o in outcomes])
win_rates = [o[1] / (o[1] + o[0]) for o in outcomes]
print(win_rates)
plt.bar(['0', '1', '2'], win_rates,
        yerr=[1.96 * math.sqrt(win_rates[i] * (1 - win_rates[i]) / sum(outcomes[i])) for i in range(3)])
print('Win rate given number of early deaths (at or below 100%):')
plt.show()

char_colors = {'peach': 'pink', 'olimar': 'bisque', 'joker': 'maroon', 'inkling': 'darkorange',
               'zero_suit_samus': 'deepskyblue', 'palutena': 'limegreen', 'fox': 'goldenrod', 'pikachu': 'yellow',
               'pokemon_trainer': 'tomato', 'mr_game_and_watch': 'black', 'wolf': 'mediumslateblue',
               'pac_man': 'yellow',
               'wario': 'gold', 'mario': 'red', 'lucina': 'royalblue', 'pichu': 'yellow', 'snake': 'slategray',
               'rob': 'firebrick', 'rosalina_and_luma': 'turquoise', 'ike': 'mediumblue', 'mega_man': 'dodgerblue'}


fig, ax = plt.subplots(1, 2, figsize=(10, 5))
ax[0].pie([character_freq[char] for char in characters], labels=characters,
          colors=[char_colors[char] for char in characters])

characters = sorted(characters, key=lambda key: -len(character_reps[key]))
ax[1].pie([len(character_reps[char]) for char in characters], labels=characters,
          colors=[char_colors[char] for char in characters])
print('Distribution of characters by raw representation (left) and number of representative players (right)')
plt.show()

fig, ax = plt.subplots(2, 1, figsize=(8, 8))
pcts = [char_kill_pcts, char_death_pcts]
titles = ['Kill percentage', 'Death percentage']
colors = [char_colors[char] for char in characters]
for i in range(2):
    ax[i].set_xticklabels(labels=characters, rotation=45, rotation_mode='anchor', verticalalignment='top',
                          horizontalalignment='right')
    ax[i].set_xlabel(titles[i])
    plot = ax[i].boxplot(pcts[i].values())
print('Distribution of kill percentages (top) and death percentages (bottom) by character')
plt.show()

def plot_with_error(x_arr, y_arr, name, color):
    x = np.mean(x_arr)
    y = np.mean(y_arr)
    xerr = 1.96 * np.std(x_arr) / math.sqrt(len(x_arr))
    yerr = 1.96 * np.std(y_arr) / math.sqrt(len(y_arr))
    plt.scatter(x, y, color=color)
    error = plt.errorbar(x, y, xerr, yerr, color=color)
    error[-1][0].set_linestyle('--')
    error[-1][1].set_linestyle('--')
    plt.annotate(name, (x, y))


fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average kill percent by character')
ax.set_ylabel('Average death percent by character')
for char in characters:
    plot_with_error(char_kill_pcts[char], char_death_pcts[char], char, char_colors[char])
plt.show()

characters = sorted(characters, key=lambda char: -character_freq[char])
mu_arr = np.array([[np.mean(matchups[char1][char2]) for char2 in characters] for char1 in characters])

fig, ax = plt.subplots(figsize=(8, 8))
# ax.imshow(mu_arr)
ax = sns.heatmap(mu_arr, xticklabels=characters, yticklabels=characters, annot=True)
plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
print('Character matchup table:')
plt.show()

mu_count = np.array([[len(matchups[char1][char2]) for char2 in characters] for char1 in characters])

fig, ax = plt.subplots(figsize=(8, 8))
# ax.imshow(mu_arr)
ax = sns.heatmap(mu_count, xticklabels=characters, yticklabels=characters, annot=True)
plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
print('Character matchup count')
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average kill percent by player')
ax.set_ylabel('Average death percent by player')
for player in players:
    plot_with_error(player_kill_pcts[player], player_death_pcts[player], player, 'gray')
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average kill percent by player-character combination')
ax.set_ylabel('Average death percent by player-character combination')
for player in player_chars:
    for char in player_chars[player]:
        plot_with_error(hybrid_kill_pcts[player][char], hybrid_death_pcts[player][char], player + "'s " + char,
                        char_colors[char])
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average stocks taken by character')
ax.set_ylabel('Average stocks lost by character')
for char in characters:
    plot_with_error(char_kills[char], char_deaths[char], char, char_colors[char])
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average stocks taken by player')
ax.set_ylabel('Average stocks lost by player')
for player in players:
    plot_with_error(player_kills[player], player_deaths[player], player, 'gray')
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average stocks taken by player-character combination')
ax.set_ylabel('Average stocks lost by player-character combination')
for player in player_chars:
    for char in player_chars[player]:
        plot_with_error(hybrid_kills[player][char], hybrid_deaths[player][char], player + "'s " + char,
                        char_colors[char])
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average damage dealt by character')
ax.set_ylabel('Average damage taken by character')
for char in characters:
    plot_with_error(char_damage_dealt[char], char_damage_taken[char], char, char_colors[char])
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average damage dealt by player')
ax.set_ylabel('Average damage taken by player')
for player in players:
    plot_with_error(player_damage_dealt[player], player_damage_taken[player], player, 'gray')
plt.show()

fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlabel('Average damage dealt by player-character combination')
ax.set_ylabel('Average damage taken by player-character combination')
for player in player_chars:
    for char in player_chars[player]:
        plot_with_error(hybrid_damage_dealt[player][char], hybrid_damage_taken[player][char], player + "'s " + char,
                        char_colors[char])
plt.show()

# print(json.dumps(matches_flat[335], indent=4))


# match_state = [[[[] for _ in range(11)] for _ in range(3)] for _ in range(3)]
#
# for t_set in matches_flat.keys():
#     for match in matches_flat[t_set]:
#         damage = [0, 0]
#
#     p1_event_data, p2_event_data = match['stats']['event_data']
#     p1_wins = len(p2_event_data['health_at_death_data']) == 3
#
#     p2_idx = 0
#     p2_stocks_lost = 0
#     for death_num in range(min(2, len(p1_event_data['health_at_death_data']))):
#         p1_death_time = p1_event_data['health_at_death_data'][death_num][0]
#         health_data = p2_event_data['health_data']
#
#         while p2_idx < len(health_data) - 1 and health_data[p2_idx + 1][0] < p1_death_time:
#             p2_idx += 1
#             if health_data[p2_idx][1] == 0:
#                 p2_stocks_lost += 1
#         p2_dmg = health_data[p2_idx][1]
#         p2_dmg_binned = min(10, p2_dmg // 20)
#         match_state[death_num + 1][p2_stocks_lost][p2_dmg_binned].append(p1_wins)
#
#     p1_idx = 0
#     p1_stocks_lost = 0
#     for death_num in range(min(2, len(p2_event_data['health_at_death_data']))):
#         p2_death_time = p2_event_data['health_at_death_data'][death_num][0]
#         health_data = p1_event_data['health_data']
#
#         while p1_idx < len(health_data) - 1 and health_data[p1_idx + 1][0] < p2_death_time:
#             p1_idx += 1
#             if health_data[p1_idx][1] == 0:
#                 p1_stocks_lost += 1
#         p1_dmg = health_data[p1_idx][1]
#         p1_dmg_binned = min(10, p1_dmg // 20)
#         if p1_stocks_lost == 3:
#             break
#         match_state[death_num + 1][p1_stocks_lost][p1_dmg_binned].append(not p1_wins)
#
# for death_num in range(1, 3):
#     for stocks_lost in range(3):
#         for dmg_bin in range(11):
#             match_state[death_num][stocks_lost][dmg_bin] = np.mean(match_state[death_num][stocks_lost][dmg_bin])
#
# print(match_state[1])
# print(match_state[2])

#     print(match['stats']['event_data'][1]['health_at_death_data'])

print("That's all! Thanks for tuning in.")
