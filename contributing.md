---
title: Contributors
layout: template
filename: contributing.md
--- 

# Contributing

Thanks for helping improve Awesome Civil Engineering. The catalog data lives in
[`data/resources.json`](data/resources.json); `README.md` is generated and should
not be edited directly.

## Add or update a resource

1. Edit the appropriate section in `data/resources.json`. Each resource requires
   a `name`, `url`, and concise `description`.
2. Install the generator dependency with `python -m pip install -r requirements.txt`.
3. Run `python generate.py`.
4. Run `python generate.py --check` before opening a pull request.

Keep entries relevant to civil engineering practice, use the resource's canonical
HTTPS URL when one is available, and avoid promotional language.

## Project contributors

### GitHub

- https://github.com/datadrivenconstruction
- https://github.com/mgreminger
- https://github.com/stoffis-git
- https://github.com/nico1993nuscheler-cloud
- https://github.com/roughed
- https://github.com/xuhp630-bot
- https://github.com/riponcm
- https://github.com/BuildQuantities
- https://github.com/keenan-fullbleed
- https://github.com/Zeetox12345

### Reddit

- u/triangleman83
- u/Rich_Carpenter8695
- u/ruffroad715
- u/tonycocacola
- u/zschwheel
- u/the_flying_condor
- u/HWDstorm
- u/h_david
- u/redabhijit
- u/StLHokie
- u/carloselunicornio
- u/WigglySpaghetti
- u/ItsAlkron
- u/frankyseven
- u/Large-At2022
- u/alpaca-miles
- u/appalachianengineer
- u/wintercity00
- u/teleportingpantaloon
- u/SoftreeTech

<style>
mark{
    color:red;
}

hr{
    color:red;
    background-color:yellow;
    height: 2px; 
    border: 0;
}

hr:hover{
    background-color:gold;
}

body{
    background-color: #24292e;
    
}

ul {
    list-style-type: square;
    list-style: none;
    list-style-type: "🥂  ";
    font-size:1.1rem;
    
}


li:hover {
    content: "•";
    color: gold;
    transform: scale(1.02);
    
    
}

h2:hover {
    transform: scale(1.02);
    animation: color-change 1s infinite;
}

h3:hover {
    transform: scale(1.02);
    animation: color-change 1s infinite;
}

h1:hover{
    animation: wiggle 1s infinite;
}

h1{
    animation: float 6s ease-in-out infinite;
}
@keyframes color-change {
  0% { color: gold; }
  50% { color: yellow; }
  100% { color: gold; }
}

@keyframes wiggle {
  0% { transform: scale(1.02); }
  50% { transform: scale(1);}
  100% { transform: scale(1.02); }
}
@keyframes float {
  0% {
    transform: translatey(0px);
  }
  50% {
    transform: translatey(-10px);
  }
  100% {
    transform: translatey(0px);
  }
}
*{
  font-family: Arial, Helvetica, sans-serif;
  animation: color-change 1s infinite;
}
a{
    color:cyan; 
}
</style>

