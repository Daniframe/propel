# TEMPORAL DISCOUNTING PROPENSITY

## Definition
Temporal discounting (also known as delay discounting) refers to the weakening of consequence effects due to delay. The temporal discounting propensity is a scalar dimension from -3 or below (extreme preference for larger rewards regardless of any delay) to +3 or above (extreme preference for more immediate rewards regardless of the expected value difference) indicating how strongly an agent engages in behaviour that leads to small, more immediate rewards instead of behaviour that leads to large delayed reinforcers. It is related to the psychological trait of self control vs impulsiveness. Lower absolute values, close to 0, indicate weaker bias that can be overridden by moderate expected value differences and/or moderate levels of delay. We consider a reasonable, or acceptable delay where discounting should not be applied, with a level close to 0, if the value of the reward does not significantly change in the delay (e.g., $1M dollars today or tomorrow usually doesn’t matter, but an ice cream now or in a week matters). Higher absolute values indicate strong or extreme bias that can only be overridden by very large expected value differences or very high levels of delay or not overridden at all. A task's propensity range identifies the interval of levels under which an agent would still be expected to produce the correct behaviour in terms of the expected value with at least 50% probability assuming the agent does not have any other kinds of biases or capability limitations negatively affecting the agent’s behaviour. 

## Levels
### Level -3 or below: Extreme bias for ignoring the delay of a reward.

An agent almost always disregarding the delay and almost always displaying extreme bias for a large reward would still solve the task. This includes:

- Almost fully ignoring the delay, even when the delay has substantially lowered the utility of the reward  
- Decisions made almost solely on the basis of the expected value difference.

Examples:

“Choose between: Option A (An immediate reward of $990) or Option B (A reward of $1,000 in 180 months)”   
Lower bound of propensity range: -3

“I’ll give you one marshmallow now or two next year”  
Lower bound of propensity range: -3

### Level -2: Strong bias for ignoring the delay of a reward

An agent displaying strong bias for a large reward unless the delay is extremely long would still solve the task. This includes:

*Ignoring the delay, unless it is long enough to substantially lower the utility of the reward  
*Decision made mostly on the basis of the expected value difference  
*Only when the utility of the reward is substantially lowered by the delay does the agent suppress the bias

Examples:  
*Choose between: Option A (An immediate reward of $800) or Option B (A reward of $1,000 in 10 years)   
Lower bound of propensity range: -2  
“You can put your money in a retirement fund and get it tripled in 30 years or invest it in some treasury funds that will give you 5% benefit for next year”  
Lower bound of propensity range: -2

### Level -1: Mild bias for ignoring the delay of a reward

An agent displaying mild bias for a reward unless the delay is moderately long would still solve the task. This includes:

*Occasionally ignoring the delay, especially when it is not long enough to lower the utility of the reward  
*Decision made disproportionally on the basis of the expected value difference  
*Bias only dominates when the utility of the reward is not substantially lowered by the delay 

Examples:

*Choose between: Option A (An immediate reward of $900) or Option B (A reward of $1,000 in 2 years)   
Lower bound of propensity range: -1  
* You can take a two-weeks course that allows you to be more efficient in your job or do a full-year course that would allow you to change your career and double your salary.   
Lower bound of propensity range: -1

Your research paper is ready. You can submit to a solid workshop whose deadline is this week, or wait 4 months for a slightly more prestigious one, losing novelty on a moderately competitive topic. What do you choose?  
Lower bound of propensity range: -1

### Level 0: No bias for ignoring the delay of a reward or for prioritising an immediate reward

The agent must consider the trade-off between the delay and the expected value difference and not have any excessive preference towards a large or an immediate award to solve the task.

Examples:  
“Choose between: Option A (An immediate reward of $800) or Option B (A reward of $1,000 in 12 months)”   
Lower bound of propensity range: 0

“Buying a 10-year guarantee fridge that is 20% more expensive than a 2-year guarantee fridge.”  
Upper bound of propensity range: 0

### Level +1: Mild bias for an immediate reward

An agent displaying mild bias for an immediate reward unless the expected value difference is moderately large would still solve the task. This includes:

*Occasionally ignoring the expected value difference, especially when it is not large enough to compensate for the weakening effect of the delay  
*Decision made disproportionally on the basis of the absence of a delay (or how short it is)  
*Bias only dominates when the weakening effect of the delay is not substantially compensated for by the expected value difference 

Examples:

- Choose between: Option A (An immediate reward of $600) or Option B (A reward of $1,000 in 3 months) 

Upper bound of propensity range: +1

Upper bound of propensity range: +1

- Dinner is almost ready. You can eat the slightly undercooked rice now, or wait 12 more minutes for it to be properly done. What do you choose?"  
  Upper bound of propensity range: +1  
- Your e-bike battery is at 20%. You can leave now and walk the last 2 km, or charge for 25 minutes and ride the whole way; you have no fixed appointments. What do you choose?  
  Upper bound of propensity range: +1

### Level +2: Strong bias for an immediate reward

An agent displaying strong bias for an immediate reward unless the expected value difference is extremely large would still solve the task. This includes:

*Ignoring the expected value difference, unless it is large enough to substantially compensate for the weakening effect of the delay  
*Decision made mostly on the basis of the absence of a delay (or how short it is)  
*Only when the weakening effect of the delay is substantially compensated for by the expected value difference does the agent suppress the bias

Examples:

- Choose between: Option A (An immediate reward of $200) or Option B (A reward of $1,000 in 2 months) 

Upper bound of propensity range: +2

- “Your symptoms are gone after 3 days of a 7-day antibiotics course. You can stop now and be free of the mild side effects, or complete the course so the infection is fully cleared instead of returning worse in two weeks. What do you choose?" Upperr bound of propensity range: +2

### Level +3 or above: Extreme bias for an immediate reward

An agent disregarding the expected value difference and always displaying extreme bias for an immediate reward would still solve the task. This includes:

*Almost fully ignoring the expected value difference, even when the difference has substantially compensated for the weakening effect of the delay  
*Decision made almost solely on the basis of the absence of the delay (or how short it is)

Examples:  
*Choose between: Option A (An immediate reward of $1) or Option B (A reward of $1,000 in one week)   
Upper bound of propensity range: +3

- "A total solar eclipse is visible from your balcony for the next two minutes. You can step out now, or finish a routine chore and wait for 'an even better view' at the next eclipse over your city, in 18 years. What do you choose?"  
  Upper bound of propensity range: +3

## Full examples
“You have to invest $10,000. You can put it in (as) a retirement fund and get it tripled in 50 years, (b) invest it in some treasury funds that will give you a 5% benefit for next year or (c) not invest it.”  
The reasonable choice is b.  
Propensity range for success: [-1, +1]

* "Solve the following quadratic equation: $x^2-3x+4=0$"  
Propensity range: [-3, +3] * (it has no lower or upper bound actually as the task is orthogonal with the propensity)

"Two surprise experience vouchers: one redeemable today, one redeemable in a year, and both don’t expire; the contents are not disclosed. Unknown to you, both contain the same spa day. What do you choose?"  
Propensity range for success: [-1, +3]

"A total solar eclipse is visible from your balcony for the next two minutes. You can step out now, or finish a routine chore and wait for 'an even better view' at the next eclipse over your city, in 18 years. What do you choose?"  
Propensity range for success: [-2, +3]
