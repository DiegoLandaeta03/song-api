import musicbrainzngs
musicbrainzngs.set_useragent("MixdTest","1.0","test")

def show(label, result):
    print("\n=== " + label + " ===")
    for r in result.get("recording-list",[]):
        score = r.get("ext:score","?")
        title = r.get("title","")
        artists = [c["artist"]["name"] for c in r.get("artist-credit",[]) if isinstance(c,dict) and "artist" in c]
        print("  [" + str(score) + "] " + title + " -- " + ", ".join(artists))

show("1. Phrase query (current)",
     musicbrainzngs.search_recordings(query='"Redbone Childish Gambino"', limit=5))
show("2. Plain free text",
     musicbrainzngs.search_recordings(query="Redbone Childish Gambino", limit=5))
show("3. Lucene field search",
     musicbrainzngs.search_recordings(query='recording:"Redbone" AND artist:"Childish Gambino"', limit=5))
show("4. Structured kwargs",
     musicbrainzngs.search_recordings(recording="Redbone", artist="Childish Gambino", limit=5))
