// save_doc.jsfl
//
// Open an existing .fla at {{FLA_PATH}}, save it in place, close
// the document. Writes a sentinel to {{SENTINEL_PATH}}.
//
// Acts as a "round-trip integrity check" — proves the file can be
// opened + saved by Animate without errors. Useful between import
// tools and as a fallback when state may be stale.
//
// Substitutions:
//   {{FLA_PATH}}       Absolute path to existing .fla.
//   {{SENTINEL_PATH}}  Absolute path for the completion sentinel.

var doc = fl.openDocument(FLfile.platformPathToURI("{{FLA_PATH}}"));
fl.saveDocument(doc);
fl.closeDocument(doc, false);

FLfile.write(FLfile.platformPathToURI("{{SENTINEL_PATH}}"), "done");
fl.quit();
