[out:json][timeout:600];
area["ISO3166-1"="TN"][admin_level=2]->.a;
(
  relation(area.a)["type"="route"]["route"~"^(bus|trolleybus|train|tram|subway|light_rail|ferry|share_taxi)$"];
  relation(area.a)["type"="route_master"];
)->.rels;
(
  node(r.rels);
  node(area.a)["public_transport"];
  node(area.a)["highway"="bus_stop"];
  node(area.a)["railway"~"^(station|halt|tram_stop|stop)$"];
  node(area.a)["amenity"~"^(bus_station|ferry_terminal)$"];
)->.stops;
(.rels; .stops;);
out body;