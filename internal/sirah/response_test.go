package sirah

import "testing"

func TestValidateResponseRejectsUnknownEmptyAndDuplicateActions(t *testing.T) {
	for _, response := range []Response{
		{Actions: []Action{"unknown"}},
		{Actions: []Action{""}},
		{Actions: []Action{ActionCenter, ActionCenter}},
		{Speech: "   "},
	} {
		if err := ValidateResponse(response); err == nil {
			t.Fatalf("response %#v was accepted", response)
		}
	}
}

func TestValidateResponseAcceptsSpeechOnlyAndKnownActions(t *testing.T) {
	if err := ValidateResponse(Response{Speech: "hola", Actions: []Action{ActionCenter, ActionBlink, ActionTired}}); err != nil {
		t.Fatal(err)
	}
}
